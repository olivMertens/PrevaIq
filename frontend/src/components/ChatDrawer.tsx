'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { X, Send, MessageSquare, Bot, Loader2 } from 'lucide-react';
import { useTranslations, useLocale } from 'next-intl';
import type { ContextLabel, ContextTask } from '@/lib/types';
import ChatHistoryPanel from './chat/ChatHistoryPanel';
import PolicyDetailModal from './chat/PolicyDetailModal';
import { useConversationRequest } from './chat/useConversationRequest';
import ChatMessageSkeleton from './chat/ChatMessageSkeleton';
import MessageBubble from './chat/MessageBubble';
import ChatModeBar from './chat/ChatModeBar';
import ChatSuggestions from './chat/ChatSuggestions';
import WorkflowPicker, { RecommendedWorkflow } from './chat/WorkflowPicker';
import WorkflowProgress from './chat/WorkflowProgress';
import { useWorkflowRequest } from './chat/useWorkflowRequest';
import { updateWorkflowExecution } from '@/lib/workflowStream';
import { useAgentCapabilities } from './chat/useAgentCapabilities';
import type { ChatMessage, ChatMode, ChatRecommendation, WorkflowExecution } from './chat/types';
import CaseTitle from './case/CaseTitle';
import { useToast } from '@/lib/ToastProvider';
import { APIError, submitFeedback } from '@/lib/api';

const PLACEHOLDER_KEYS: Record<ChatMode, string> = {
  auto: 'placeholderAuto',
  data: 'placeholderData',
  policy: 'placeholderPolicy',
  analysis: 'placeholderAnalysis',
  dashboard: 'placeholderDashboard',
  workflow: 'placeholderWorkflow',
};

interface ChatDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onOpen: () => void;
  applicationId: string;
  persona?: string;  // Persona type for RAG context
  contextLabels?: ContextLabel[];  // Backend-driven dossier context labels
  contextTasks?: ContextTask[];    // Backend-driven dossier action items
  applicationStatus?: string;     // 'pending' | 'extracted' | 'completed' | 'error'
  processingStatus?: string | null; // 'extracting' | 'analyzing' | null
  hasDecision?: boolean;           // Whether a decision has been taken on this dossier
  caseTitle?: string;              // Full case title, shown compact in the header
  initialConversationId?: string | null; // Conversation to open on mount (link from another case)
}

export default function ChatDrawer({
  isOpen,
  onClose,
  onOpen,
  applicationId,
  persona = 'underwriting',
  contextLabels,
  contextTasks,
  applicationStatus,
  processingStatus,
  hasDecision,
  caseTitle,
  initialConversationId,
}: ChatDrawerProps) {
  const { addToast } = useToast();
  const t = useTranslations('chat');
  const locale = useLocale();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const requestGenerationRef = useRef(0);
  const { send: sendChatRequest, cancel: cancelChatRequest } = useConversationRequest(applicationId);
  const { run: runWorkflowRequest, cancel: cancelWorkflowRequest } = useWorkflowRequest(applicationId);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string>(t('newChat'));
  const [historyCollapsed, setHistoryCollapsed] = useState(true);
  const [useCorrections, setUseCorrections] = useState(true);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [workflowRunning, setWorkflowRunning] = useState<string | null>(null);
  const [workflowExecution, setWorkflowExecution] = useState<WorkflowExecution>({ plan: [], context: 'waiting', agents: {} });
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
  // Free questions go to the Auto agent by default; workflows are one click away.
  const [activeAgent, setActiveAgent] = useState<ChatMode>('auto');
  const [llmSuggestions, setLlmSuggestions] = useState<string[]>([]);
  const capabilities = useAgentCapabilities(isOpen);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // ── LLM-generated dynamic suggestions (dossier-aware pills) ──
  // Fetches 3-4 questions tailored to THIS dossier from the backend.
  // Falls back silently to the deterministic rules below if the call fails.
  useEffect(() => {
    // Reset on dossier / agent / context change so stale pills don't linger
    setLlmSuggestions([]);

    if (!isOpen || !applicationId) return;
    // Skip while extraction/analysis still in progress — too little signal.
    if (processingStatus === 'extracting' || processingStatus === 'analyzing') return;
    // Specific agent pills (data/policy/analysis/dashboard) have their own static suggestions.
    if (activeAgent !== 'auto') return;

    const controller = new AbortController();
    const t0 = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/applications/${applicationId}/chat/suggestions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ language: locale, agent: activeAgent }),
          signal: controller.signal,
        });
        if (!resp.ok) return;
        const data = await resp.json();
        if (Array.isArray(data?.suggestions) && data.suggestions.length > 0) {
          setLlmSuggestions(data.suggestions.filter((s: unknown) => typeof s === 'string'));
        }
      } catch {
        /* silent — fallback to deterministic rules */
      }
    }, 250); // small debounce to avoid bursts on rapid context updates

    return () => {
      clearTimeout(t0);
      controller.abort();
    };
  }, [
    isOpen,
    applicationId,
    activeAgent,
    locale,
    processingStatus,
    applicationStatus,
    hasDecision,
    // Re-fetch when dossier context materially changes
    contextLabels?.length,
    contextTasks?.length,
  ]);

  // Contextual suggestions — lifecycle-aware + backend context labels/tasks
  // ── Smart recommendation engine — analyzes dossier to recommend best workflow/agent ──
  const recommendations = useMemo(() => {
    if (applicationStatus !== 'extracted' && applicationStatus !== 'completed') return [];
    
    const labelKeys = new Set((contextLabels || []).map(l => l.key));
    const labelTypes = new Set((contextLabels || []).map(l => l.type));
    const taskCategories = new Set((contextTasks || []).map(t => t.category));
    const hasFraud = labelTypes.has('fraud');
    const hasSIU = labelKeys.has('fraude_elevee') || labelKeys.has('renvoi_siu');
    const isMajor = labelKeys.has('sinistre_majeur');
    const hasCatNat = labelKeys.has('regime_catnat') || labelKeys.has('catnat_non_confirmee');
    const hasMissingDocs = taskCategories.has('documents');
    const hasRecourse = taskCategories.has('recourse') || labelKeys.has('rc_habitation');
    const hasExpertise = taskCategories.has('expertise');
    const hasMortgageRisk =
      labelKeys.has('hcsf_endettement_critique')
      || labelKeys.has('hcsf_endettement_tendu')
      || labelKeys.has('hcsf_ltv_critique')
      || labelKeys.has('hcsf_ltv_tendu')
      || labelKeys.has('credit_score_faible');
    const hasMortgageDocs = labelKeys.has('pieces_manquantes') || taskCategories.has('documents');
    const isMortgagePersona = persona === 'mortgage' || persona === 'mortgage_underwriting';

    type Rec = ChatRecommendation;
    const recs: Rec[] = [];

    // Fraude workflow — high fraud indicators
    if (hasFraud || hasSIU) {
      recs.push({ id: 'fraude', score: hasSIU ? 95 : 80, reason: hasSIU ? t('recSIU') : t('recFraud') });
    }

    // Complet workflow — complex case
    if (isMajor || hasRecourse || hasExpertise || hasCatNat || (contextLabels && contextLabels.length > 3)) {
      const score = (isMajor ? 25 : 0) + (hasRecourse ? 20 : 0) + (hasExpertise ? 15 : 0) + (hasCatNat ? 15 : 0) + ((contextLabels?.length || 0) > 3 ? 10 : 0);
      recs.push({ id: 'complet', score: Math.min(90, 50 + score), reason: [
        isMajor && t('recommendationSignals.majorClaim'),
        hasRecourse && t('recommendationSignals.thirdPartyRecourse'),
        hasExpertise && t('recommendationSignals.expertiseRequired'),
        hasCatNat && t('recommendationSignals.catNat'),
      ].filter(Boolean).join(' + ') + ' — ' + t('recComplet') });
    }

    // Express workflow — routine/simple case
    if (!isMajor && !hasSIU && !hasCatNat && (contextLabels?.length || 0) <= 3) {
      recs.push({ id: 'express', score: hasFraud ? 40 : 70, reason: t('recExpress') });
    }

    // Also recommend specific agent pills based on context
    if (hasMissingDocs) recs.push({ id: 'agent:analysis', score: 60, reason: t('recMissing') });
    if (hasRecourse) recs.push({ id: 'agent:policy', score: 55, reason: t('recRecourse') });
    if (isMortgagePersona && hasMortgageRisk) {
      recs.push({ id: 'agent:analysis', score: 75, reason: t('recMortgageHcsf') });
      recs.push({ id: 'complet', score: 70, reason: t('recMortgageSensitive') });
    }
    if (isMortgagePersona && hasMortgageDocs) {
      recs.push({ id: 'agent:analysis', score: 68, reason: t('recMortgageDocuments') });
    }

    return recs.sort((a, b) => b.score - a.score);
  }, [applicationStatus, contextLabels, contextTasks, persona, t]);

  const contextualSuggestions = useMemo(() => {
    // State-aware suggestions based on dossier lifecycle
    if (processingStatus === 'extracting') {
      return [t('contextual.extracting')];
    }
    if (processingStatus === 'analyzing') {
      return [t('contextual.analyzing')];
    }
    if (applicationStatus === 'error') {
      return [
        t('contextual.processingFailed'),
        t('contextual.summarizeError'),
      ];
    }

    // Pill-specific suggestions — override context-based ones
    if (activeAgent === 'data') {
      return [t('suggestionDataStats'), t('suggestionDataAmount'), t('suggestionDataFrequency'), t('suggestionDataTrend')];
    }
    if (activeAgent === 'policy') {
      return [t('suggestionPolicyCoverage'), t('suggestionPolicyExclusion'), t('suggestionPolicyFranchise'), t('suggestionPolicyIRSI')];
    }
    if (activeAgent === 'analysis') {
      return [t('suggestionAnalysisRisk'), t('suggestionAnalysisLiability'), t('suggestionAnalysisConsistency')];
    }
    if (activeAgent === 'dashboard') {
      return [t('suggestionKPIOverview'), t('suggestionKPITimeline'), t('suggestionKPIHistory')];
    }

    // ── LLM-generated suggestions take priority when available (auto agent only) ──
    if (llmSuggestions.length > 0) {
      return llmSuggestions;
    }

    const suggestions: string[] = [];

    // Post-decision suggestions
    if (hasDecision) {
      suggestions.push(t('contextual.summarizeDecision'));
      suggestions.push(t('contextual.nextSteps'));
    }

    // Generate suggestions from context labels (dossier-specific)
    if (contextLabels && contextLabels.length > 0) {
      const labelTypes = new Set(contextLabels.map(l => l.type));
      const labelKeys = new Set(contextLabels.map(l => l.key));

      if (labelKeys.has('convention_irsi')) suggestions.push(t('contextual.irsi'));
      if (labelKeys.has('garantie_dde')) suggestions.push(t('contextual.waterDeductible'));
      if (labelKeys.has('garantie_tempete')) suggestions.push(t('contextual.stormCoverage'));
      if (labelKeys.has('garantie_vol')) suggestions.push(t('contextual.theftCoverage'));
      if (labelKeys.has('garantie_incendie')) suggestions.push(t('contextual.fireExclusions'));
      if (labelKeys.has('rc_habitation')) suggestions.push(t('contextual.thirdPartyRecourse'));
      if (labelKeys.has('regime_catnat')) suggestions.push(t('contextual.catNatOrder'));
      if (labelKeys.has('sinistre_majeur')) suggestions.push(t('contextual.expertiseThresholds'));
      if (labelTypes.has('fraud')) {
        suggestions.push(t('contextual.fraudIndicators'));
        suggestions.push(t('contextual.photoAuthenticity'));
      }
      if (labelKeys.has('catnat_confirmee') || labelKeys.has('catnat_non_confirmee')) {
        suggestions.push(t('contextual.catNatConditions'));
      }
      if (labelKeys.has('exclusions_possibles')) suggestions.push(t('contextual.possibleExclusions'));
      if (labelKeys.has('couverture_non_confirmee')) suggestions.push(t('contextual.coverageConfirmed'));

      if (labelKeys.has('hcsf_endettement_critique') || labelKeys.has('hcsf_endettement_tendu')) {
        suggestions.push(t('contextual.hcsfDebt'));
      }
      if (labelKeys.has('hcsf_ltv_critique') || labelKeys.has('hcsf_ltv_tendu')) {
        suggestions.push(t('contextual.ltv'));
      }
      if (labelKeys.has('hcsf_apport_faible')) {
        suggestions.push(t('contextual.downPayment'));
      }
      if (labelKeys.has('ptz')) {
        suggestions.push(t('contextual.ptz'));
      }
      if (labelKeys.has('frontalier')) {
        suggestions.push(t('contextual.crossBorder'));
      }
      if (labelKeys.has('pieces_manquantes')) {
        suggestions.push(t('contextual.missingDocuments'));
      }
    }

    // Generate from context tasks
    if (contextTasks && contextTasks.length > 0) {
      for (const task of contextTasks) {
        if (task.category === 'coverage')
          suggestions.push(t('contextual.summarizeCoverage'));
        else if (task.category === 'expertise')
          suggestions.push(t('contextual.expertType'));
        else if (task.category === 'recourse')
          suggestions.push(t('contextual.recourseProcedure'));
        else if (task.category === 'documents')
          suggestions.push(t('contextual.documentsNeeded'));
        else if (task.category === 'fraud')
          suggestions.push(t('contextual.summarizeFraud'));
        else if (task.category === 'verification')
          suggestions.push(t('contextual.regulatoryChecks'));
        else if (task.category === 'risk')
          suggestions.push(t('contextual.riskSignals'));
      }
    }

    const unique = [...new Set(suggestions)];
    if (unique.length > 0) return unique;

    // Persona-based fallback (pre-analysis or non-claims personas)
    const fallback: Record<string, string[]> = {
      habitation_claims: [
        t('contextual.propertyCoverage'),
        t('contextual.applicableDeductible'),
        t('contextual.detectPhotoFraud'),
      ],
      property_casualty_claims: [
        t('contextual.propertyCoverage'),
        t('contextual.applicableDeductible'),
      ],
      automotive_claims: [
        t('contextual.insuredLiability'),
        t('contextual.detectPhotoFraud'),
      ],
      life_health_claims: [
        t('contextual.healthCoverage'),
        t('contextual.reimbursementRate'),
      ],
      underwriting: [
        t('contextual.cardiovascularRisk'),
        t('contextual.recommendedPlan'),
      ],
      mortgage: [
        t('contextual.ltvShort'),
        t('contextual.debtCompliant'),
        t('contextual.hcsfRisk'),
      ],
    };
    return fallback[persona] || fallback.habitation_claims || [];
  }, [persona, contextLabels, contextTasks, applicationStatus, processingStatus, hasDecision, activeAgent, llmSuggestions, t]);

  // Handle clicking on a policy citation to open the detail modal
  const handlePolicyClick = useCallback((policyId: string) => {
    setSelectedPolicyId(policyId);
  }, []);

  // Handle feedback (thumbs up / thumbs down)
  const handleFeedback = useCallback(async (msg: ChatMessage, type: 'positive' | 'negative') => {
    // Update UI immediately
    setMessages(prev => prev.map(m =>
      m === msg ? { ...m, feedbackGiven: type } : m
    ));

    try {
      await submitFeedback({
        agent_type: 'chat',
        feedback_type: type,
        original_query: msg.userQuery || undefined,
        agent_response: msg.content,
        persona,
        conversation_id: conversationId || undefined,
        application_id: applicationId,
      });
    } catch {
      // Revert on failure
      setMessages(prev => prev.map(m =>
        m === msg ? { ...m, feedbackGiven: null } : m
      ));
      addToast('error', t('feedbackError'));
    }
  }, [persona, conversationId, applicationId, addToast, t]);

  // Reset state when application changes
  useEffect(() => {
    requestGenerationRef.current += 1;
    cancelChatRequest();
    cancelWorkflowRequest();
    setWorkflowRunning(null);
    setMessages([]);
    setConversationId(null);
    setConversationTitle(t('newChat'));
    setIsLoading(false);
  }, [applicationId, t, cancelChatRequest, cancelWorkflowRequest]);

  // Ignore late answers after unmount
  useEffect(() => {
    return () => {
      requestGenerationRef.current += 1;
    };
  }, []);

  // Load a specific conversation
  const loadConversation = useCallback(async (convId: string | null) => {
    const generation = ++requestGenerationRef.current;
    cancelChatRequest();
    cancelWorkflowRequest();
    setWorkflowRunning(null);
    setIsLoading(false);
    if (!convId) {
      // Start new conversation
      setMessages([]);
      setConversationId(null);
      setConversationTitle(t('newChat'));
      return;
    }

    setIsLoadingConversation(true);
    try {
      // Use relative path to go through Next.js proxy
      const response = await fetch(
        `/api/applications/${encodeURIComponent(applicationId)}/conversations/${encodeURIComponent(convId)}`
      );
      
      if (response.ok) {
        const data = await response.json();
        if (generation !== requestGenerationRef.current) return;
        setMessages(
          (data.messages || []).map((m: ChatMessage & { timestamp: string }) => ({
            ...m,
            timestamp: new Date(m.timestamp),
          }))
        );
        setConversationId(data.id);
        setConversationTitle(data.title || t('conversation'));
      } else if (generation === requestGenerationRef.current) {
        addToast('error', t('conversationLoadError'));
      }
    } catch (e) {
      if (generation !== requestGenerationRef.current) return;
      console.error('Failed to load conversation:', e);
      addToast('error', t('conversationLoadError'));
    } finally {
      if (generation === requestGenerationRef.current) setIsLoadingConversation(false);
    }
  }, [applicationId, addToast, t, cancelChatRequest, cancelWorkflowRequest]);

  // Conversation opened from another case's history (?conversation= link)
  const openedConversationRef = useRef<string | null>(null);
  useEffect(() => {
    if (!initialConversationId || openedConversationRef.current === initialConversationId) return;
    openedConversationRef.current = initialConversationId;
    loadConversation(initialConversationId);
  }, [initialConversationId, loadConversation]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, workflowRunning]);

  // Focus input when drawer opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, onClose]);

  // ── Workflow execution handler ──
  const handleWorkflow = useCallback(async (workflowId: string, workflowName: string) => {
    if (isLoading || workflowRunning) return;
    const generation = ++requestGenerationRef.current;
    setWorkflowRunning(workflowId);
    let execution: WorkflowExecution = { plan: [], context: 'waiting', agents: {} };
    setWorkflowExecution(execution);
    const started = Date.now();
    setMessages(prev => [...prev, {
      role: 'user',
      content: t('workflowRequest', { name: workflowName }),
      timestamp: new Date(),
    }]);

    try {
      const result = await runWorkflowRequest(workflowId, locale, event => {
        if (generation !== requestGenerationRef.current) return;
        execution = updateWorkflowExecution(execution, event);
        setWorkflowExecution(execution);
      });
      if (!result || generation !== requestGenerationRef.current) return;
      const { steps, summary } = result;
      if (!execution.plan.length && result.plan) {
        execution = {
          plan: result.plan, context: 'completed',
          agents: Object.fromEntries(steps.map(step => [step.agent, {
            status: /requires_human_review['"`*]*\s*:\s*true/i.test(step.text) ? 'needs_review' : 'completed',
          }])),
        };
      }
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: summary,
        timestamp: new Date(),
        workflow: {
          id: workflowId,
          name: workflowName,
          status: result.status === 'needs_review' ? 'needs_review' : 'completed',
          steps,
          summary,
          durationMs: Date.now() - started,
          execution: execution.plan.length ? execution : undefined,
        },
      }]);
    } catch (err) {
      if (generation !== requestGenerationRef.current) return;
      console.error('Workflow request failed:', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `**${t('workflowErrorTitle')}** — ${t(err instanceof APIError && err.status === 504 ? 'workflowTimeout' : 'workflowStreamError')}`,
        timestamp: new Date(),
      }]);
    } finally {
      if (generation === requestGenerationRef.current) setWorkflowRunning(null);
    }
  }, [isLoading, locale, runWorkflowRequest, t, workflowRunning]);

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading || workflowRunning) return;
    const generation = ++requestGenerationRef.current;

    const userMessage: ChatMessage = {
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      // Workflows run from their cards; a question typed in that mode goes to the Auto agent.
      const agentType = activeAgent === 'workflow' || (activeAgent === 'data' && !capabilities.fabric_data)
        ? 'auto'
        : activeAgent;
      const data = await sendChatRequest({
        message: userMessage.content,
        conversation_id: conversationId,
        persona,
        agent_type: agentType,
        use_corrections: useCorrections,
        language: locale,
      });
      if (!data || generation !== requestGenerationRef.current) return;

      // Update conversation ID if this was a new conversation
      if (!conversationId && data.conversation_id) {
        setConversationId(data.conversation_id);
        setConversationTitle(data.title || t('newChat'));
        // Refresh the history panel
        void window.__refreshChatHistory?.();
      }

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: new Date(),
        rag: data.rag, // Capture RAG metadata from response
        agent: data.agent, // Capture agent metadata
        userQuery: userMessage.content, // Track which question this answers
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      if (generation !== requestGenerationRef.current) return;
      const code = error instanceof APIError ? error.code : undefined;
      const errorKeys: Record<string, string> = {
        AI_DEPLOYMENT_NOT_FOUND: 'modelUnavailable',
        AI_AUTHENTICATION_ERROR: 'modelUnavailable',
        AI_TIMEOUT: 'requestTimeout',
        AI_SERVICE_UNAVAILABLE: 'serviceUnavailable',
        AI_EMPTY_RESPONSE: 'emptyResponse',
      };
      let message = t(errorKeys[code ?? ''] ?? 'communicationError');
      if (error instanceof APIError && error.requestId) {
        message += ` ${t('errorReference', { id: error.requestId })}`;
      }
      addToast('error', message);
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: message,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      if (generation === requestGenerationRef.current) {
        setIsLoading(false);
      }
    }
  }, [
    inputValue,
    isLoading,
    workflowRunning,
    conversationId,
    persona,
    activeAgent,
    capabilities.fabric_data,
    useCorrections,
    t,
    addToast,
    sendChatRequest,
    locale,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewConversation = () => {
    requestGenerationRef.current += 1;
    cancelChatRequest();
    cancelWorkflowRequest();
    setWorkflowRunning(null);
    setIsLoading(false);
    setIsLoadingConversation(false);
    setMessages([]);
    setConversationId(null);
    setConversationTitle(t('newChat'));
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleSelectConversation = (id: string | null, convApplicationId?: string, convPersona?: string) => {
    // A conversation of another case opens that case, with the chat on this conversation.
    if (id && convApplicationId && convApplicationId !== applicationId) {
      const params = new URLSearchParams({ app: convApplicationId, conversation: id });
      if (convPersona) params.set('persona', convPersona);
      window.location.href = `/?${params.toString()}`;
      return;
    }
    loadConversation(id);
  };

  const canRunWorkflows = applicationStatus === 'completed' || applicationStatus === 'extracted';
  const busy = isLoading || !!workflowRunning;
  const isEmpty = messages.length === 0 && !isLoadingConversation;

  return (
    <>
      {/* Floating Button - visible when drawer is closed */}
      <button
        onClick={onOpen}
        className={`fixed bottom-6 right-6 z-40 flex items-center gap-2.5 px-5 py-3 bg-indigo-600 text-white rounded-full shadow-lg hover:bg-indigo-700 hover:shadow-xl transition-all duration-300 group whitespace-nowrap ${
          isOpen ? 'opacity-0 pointer-events-none translate-x-4' : 'opacity-100 translate-x-0'
        }`}
        title={t('askIQ')}
      >
        <MessageSquare className="w-5 h-5 flex-shrink-0" />
        <span className="font-medium text-sm">{t('askIQ')}</span>
      </button>

      {/* Backdrop */}
      <div
        className={`fixed inset-0 bg-black/20 z-40 transition-opacity duration-300 ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        ref={drawerRef}
        className={`fixed right-0 top-0 h-full w-full max-w-4xl bg-white shadow-2xl z-50 flex transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* History Panel */}
        <ChatHistoryPanel
          applicationId={applicationId}
          currentConversationId={conversationId}
          onSelectConversation={handleSelectConversation}
          onNewConversation={handleNewConversation}
          isCollapsed={historyCollapsed}
          onToggleCollapse={() => setHistoryCollapsed(!historyCollapsed)}
        />

        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between gap-3 bg-slate-50">
            <div className="flex min-w-0 items-center gap-3">
              <div className="w-8 h-8 flex-none bg-indigo-100 rounded-lg flex items-center justify-center">
                <MessageSquare className="w-5 h-5 text-indigo-600" />
              </div>
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-slate-900" title={conversationTitle}>
                  {conversationTitle}
                </h2>
                {caseTitle ? (
                  <CaseTitle title={caseTitle} className="text-xs text-slate-600" />
                ) : (
                  <p className="text-xs text-slate-500">
                    {conversationId ? t('messagesCount', { count: messages.length }) : t('startNewConversation')}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              title={t('closeChat')}
              aria-label={t('closeChat')}
              className="flex-none p-2 hover:bg-slate-200 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-slate-500" />
            </button>
          </div>

          {/* Messages */}
          <div className="min-h-0 flex-1 overflow-y-auto p-4 space-y-4" aria-busy={isLoading || isLoadingConversation}>
            {isLoadingConversation ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
              </div>
            ) : isEmpty ? (
              <div className="text-center py-3">
                <Bot className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                <p className="text-sm text-slate-500">
                  {t('emptyStateAsk')}
                </p>
                {contextualSuggestions.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <p className="text-xs text-slate-400">{t('tryForExample')}</p>
                    <ChatSuggestions suggestions={contextualSuggestions}
                      onSelect={suggestion => { setInputValue(suggestion); inputRef.current?.focus(); }} />
                  </div>
                )}
                {canRunWorkflows && activeAgent !== 'workflow' && (
                  <RecommendedWorkflow recommendations={recommendations} disabled={busy} onRun={handleWorkflow} />
                )}
              </div>
            ) : (
              messages.map((msg, idx) => (
                <MessageBubble key={idx} msg={msg} onPolicyClick={handlePolicyClick} onFeedback={handleFeedback} />
              ))
            )}
            
            {isLoading && <ChatMessageSkeleton />}

            {workflowRunning && <WorkflowProgress execution={workflowExecution} />}
            
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="shrink-0 p-3 border-t border-slate-200 bg-white">
            <ChatModeBar
              mode={activeAgent}
              onModeChange={setActiveAgent}
              fabricAvailable={capabilities.fabric_data}
              useCorrections={useCorrections}
              onToggleCorrections={() => setUseCorrections(prev => !prev)}
            />
            {/* Fabric indicator */}
            {activeAgent === 'data' && (
              <div className="flex items-center gap-1.5 mb-1.5 px-1">
                <svg className="w-3 h-3 flex-shrink-0" viewBox="0 0 16 16" fill="none">
                  <path d="M8 1L14.5 5v6L8 15 1.5 11V5L8 1z" fill="#E8680C" opacity="0.85"/>
                  <path d="M8 1L14.5 5 8 9 1.5 5 8 1z" fill="#F59E0B"/>
                </svg>
                <span className="text-[10px] text-orange-600 font-medium">
                  {t('poweredByFabric')}
                </span>
              </div>
            )}
            {/* Suggestions: in the empty state above, here once the conversation has started */}
            {!isEmpty && contextualSuggestions.length > 0 && !busy && activeAgent !== 'workflow' && (
              <ChatSuggestions suggestions={contextualSuggestions} compact
                onSelect={suggestion => { setInputValue(suggestion); inputRef.current?.focus(); }} />
            )}
            {activeAgent === 'workflow' && (
              <WorkflowPicker
                recommendations={recommendations}
                available={canRunWorkflows}
                disabled={busy}
                onRun={handleWorkflow}
                onPickMode={setActiveAgent}
              />
            )}
            <div className="flex gap-2">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t(PLACEHOLDER_KEYS[activeAgent])}
                className="flex-1 resize-none rounded-lg border border-slate-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                rows={2}
                disabled={isLoading}
              />
              <button
                onClick={handleSend}
                disabled={!inputValue.trim() || isLoading}
                title={t('sendMessage')}
                aria-label={t('sendMessage')}
                className="self-end px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              {t('enterToSendHint')}
            </p>
          </div>
        </div>
      </div>

      {/* Policy Detail Modal */}
      {selectedPolicyId && (
        <PolicyDetailModal
          policyId={selectedPolicyId}
          persona={persona}
          onClose={() => setSelectedPolicyId(null)}
        />
      )}
    </>
  );
}
