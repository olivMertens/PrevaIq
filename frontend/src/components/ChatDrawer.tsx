'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { X, Send, MessageSquare, Bot, User, Loader2, Info, BookOpen, ChevronDown, ChevronUp, ExternalLink, ThumbsUp, ThumbsDown, Database, Shield, FileSearch, FileText, BarChart3, Globe, Workflow } from 'lucide-react';
import { useTranslations, useLocale } from 'next-intl';
import type { ContextLabel, ContextTask } from '@/lib/types';
import { StructuredContentRenderer } from './chat/ChatCards';
import ChatHistoryPanel from './chat/ChatHistoryPanel';
import PolicyDetailModal from './chat/PolicyDetailModal';
import { useConversationRequest } from './chat/useConversationRequest';
import ChatMessageSkeleton from './chat/ChatMessageSkeleton';
import { useToast } from '@/lib/ToastProvider';
import { APIError, submitFeedback } from '@/lib/api';

// Citation data from RAG response
interface RAGCitation {
  policy_id: string;
  policy_name: string;
  chunk_type: string;
  criteria_id?: string;
}

// RAG metadata from API response
interface RAGMetadata {
  enabled: boolean;
  chunks_retrieved?: number;
  tokens_used?: number;
  latency_ms?: number;
  citations?: RAGCitation[];
  inferred_categories?: string[];
  fallback?: boolean;
  fallback_reason?: string;
}

// Agent metadata from API response
interface AgentMetadata {
  name: string;
  tools_available?: string[];
  tools_called?: string[];
  framework?: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  rag?: RAGMetadata;
  agent?: AgentMetadata;
  feedbackGiven?: 'positive' | 'negative' | null;
  userQuery?: string; // The user query this assistant message responds to
}

// Loading status phases
type LoadingPhase = 'retrieving' | 'analyzing' | 'formulating' | string | null;

// RAG Stats Tooltip Component
function RAGStatsTooltip({ rag }: { rag: RAGMetadata }) {
  const [isVisible, setIsVisible] = useState(false);
  const t = useTranslations('chat');
  
  if (!rag?.enabled || rag.fallback) return null;
  
  return (
    <div className="relative inline-block ml-1">
      <button
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
        onClick={() => setIsVisible(!isVisible)}
        className="text-slate-400 hover:text-indigo-500 transition-colors"
        aria-label={t('viewRagStats')}
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      
      {isVisible && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50">
          <div className="bg-slate-800 text-white text-xs rounded-lg shadow-lg p-3 min-w-[180px]">
            <div className="font-semibold mb-2 text-indigo-300">{t('ragStats')}</div>
            <div className="space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-300">{t('chunksRetrieved')}</span>
                <span className="font-mono">{rag.chunks_retrieved || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-300">{t('tokensUsed')}</span>
                <span className="font-mono">{rag.tokens_used || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-300">{t('latency')}</span>
                <span className="font-mono">{rag.latency_ms || 0}ms</span>
              </div>
              {rag.inferred_categories && rag.inferred_categories.length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-600">
                  <span className="text-slate-300">{t('categories')}</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {rag.inferred_categories.map((cat, i) => (
                      <span key={i} className="px-1.5 py-0.5 bg-indigo-600/30 rounded text-indigo-200 text-[10px]">
                        {cat}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {/* Tooltip arrow */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800" />
          </div>
        </div>
      )}
    </div>
  );
}

// Expandable Citations Component with clickable policy viewer
function PolicyCitations({ 
  citations, 
  onPolicyClick 
}: { 
  citations?: RAGCitation[];
  onPolicyClick?: (policyId: string) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const t = useTranslations('chat');
  
  if (!citations || citations.length === 0) return null;
  
  // Get unique policies
  const uniquePolicies = Array.from(
    new Map(citations.map(c => [c.policy_id, c])).values()
  );
  
  const handleCitationClick = (policyId: string) => {
    if (onPolicyClick) {
      onPolicyClick(policyId);
    }
  };
  
  return (
    <div className="mt-2 pt-2 border-t border-slate-200">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700 transition-colors"
      >
        <BookOpen className="w-3.5 h-3.5" />
        <span>{t('policiesReferenced', { count: uniquePolicies.length })}</span>
        {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      
      {isExpanded && (
        <div className="mt-2 space-y-1">
          {uniquePolicies.map((citation, idx) => (
            <div
              key={idx}
              className="relative"
              onMouseEnter={() => setHoveredIdx(idx)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              <button
                onClick={() => handleCitationClick(citation.policy_id)}
                className="w-full flex items-center justify-between gap-2 text-xs bg-slate-50 rounded px-2 py-1.5 cursor-pointer hover:bg-indigo-50 hover:border-indigo-200 border border-transparent transition-colors text-left"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono text-indigo-600">{citation.policy_id}</span>
                  <span className="text-slate-500 truncate">{citation.policy_name}</span>
                </div>
                <ExternalLink className="w-3 h-3 text-slate-400 flex-shrink-0" />
              </button>
              
              {/* Hover tooltip with details */}
              {hoveredIdx === idx && (
                <div className="absolute left-0 bottom-full mb-1 z-50 bg-white border border-slate-200 rounded-lg shadow-lg p-3 min-w-[250px] max-w-[350px]">
                  <div className="font-semibold text-sm text-slate-800">{citation.policy_name}</div>
                  <div className="mt-1 space-y-1 text-xs">
                    <div className="flex gap-2">
                      <span className="text-slate-500">{t('policyId')}</span>
                      <span className="font-mono text-indigo-600">{citation.policy_id}</span>
                    </div>
                    <div className="flex gap-2">
                      <span className="text-slate-500">{t('chunkType')}</span>
                      <span className="capitalize">{citation.chunk_type}</span>
                    </div>
                    {citation.criteria_id && (
                      <div className="flex gap-2">
                        <span className="text-slate-500">{t('criteriaId')}</span>
                        <span className="font-mono">{citation.criteria_id}</span>
                      </div>
                    )}
                  </div>
                  <div className="mt-2 pt-2 border-t border-slate-100 text-xs text-indigo-600">
                    {t('clickToViewPolicy')}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Agent badge config — maps tool names & agent hints to display badges
const TOOL_BADGES: Record<string, { label: string; color: string; icon: typeof Bot }> = {
  search_policies: { label: 'Polices RAG', color: 'bg-amber-100 text-amber-700', icon: Shield },
  get_application_summary: { label: 'Données', color: 'bg-emerald-100 text-emerald-700', icon: Database },
  get_glossary: { label: 'Glossaire', color: 'bg-violet-100 text-violet-700', icon: BookOpen },
  query_fabric_data: { label: 'Fabric', color: 'bg-cyan-100 text-cyan-700', icon: BarChart3 },
  analyze_image_fraud: { label: 'Détection Fraude', color: 'bg-purple-100 text-purple-700', icon: Shield },
  web_search: { label: 'Web Search', color: 'bg-blue-100 text-blue-700', icon: Globe },
  webiq_search: { label: 'Web IQ', color: 'bg-blue-100 text-blue-700', icon: Globe },
};

// Detect which agents/tools contributed to a response
function detectAgentBadges(msg: ChatMessage): { label: string; color: string; icon: typeof Bot }[] {
  const badges: { label: string; color: string; icon: typeof Bot }[] = [];

  // From RAG citations
  if (msg.rag?.citations && msg.rag.citations.length > 0) {
    badges.push(TOOL_BADGES.search_policies);
  }

  for (const tool of msg.agent?.tools_called ?? []) {
    if (TOOL_BADGES[tool]) badges.push(TOOL_BADGES[tool]);
  }

  // Deduplicate by label
  const seen = new Set<string>();
  return badges.filter(b => { if (seen.has(b.label)) return false; seen.add(b.label); return true; });
}

// Quick-link toolbox for policy PDFs referenced in message
function PolicyToolbox({ content, citations }: { content: string; citations?: RAGCitation[] }) {
  // Collect policy IDs from inline references (e.g. PC-COV-001) and from RAG citations
  const policyIds = new Set<string>();
  const inlineMatches = content.match(/\b[A-Z]+-[A-Z]+-\d+\b/g);
  if (inlineMatches) inlineMatches.forEach(id => policyIds.add(id));
  if (citations) citations.forEach(c => policyIds.add(c.policy_id));

  if (policyIds.size === 0) return null;

  // Map policy ID prefixes to PDF filenames and labels
  const policyPdfMap: Record<string, { label: string; pdf: string }> = {
    'PC': { label: 'CG Habitation', pdf: 'habitation' },
    'LH': { label: 'CG Santé', pdf: 'sante' },
    'AU': { label: 'CG Auto', pdf: 'auto' },
    'MO': { label: 'CG Hypothécaire', pdf: 'hypothecaire' },
  };

  // Group by PDF
  const pdfLinks = new Map<string, { label: string; pdf: string; ids: string[] }>();
  for (const id of policyIds) {
    const prefix = id.split('-')[0];
    const mapping = policyPdfMap[prefix];
    if (mapping) {
      const existing = pdfLinks.get(mapping.pdf);
      if (existing) {
        existing.ids.push(id);
      } else {
        pdfLinks.set(mapping.pdf, { ...mapping, ids: [id] });
      }
    }
  }

  if (pdfLinks.size === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-1.5 pt-1.5 border-t border-slate-200/80">
      <FileText className="w-3 h-3 text-slate-400 flex-shrink-0" />
      {Array.from(pdfLinks.values()).map(({ label, pdf, ids }) => (
        <a
          key={pdf}
          href={`/api/policy-pdfs/${pdf}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-slate-50 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-300 rounded text-[10px] font-medium text-slate-600 hover:text-indigo-700 transition-colors"
          title={`Ouvrir ${label} — Références: ${ids.join(', ')}`}
        >
          <ExternalLink className="w-2.5 h-2.5" />
          {label}
          <span className="text-slate-400">({ids.length})</span>
        </a>
      ))}
    </div>
  );
}

// Message Bubble Component with RAG enhancements
function MessageBubble({ 
  msg, 
  onPolicyClick,
  onFeedback,
}: { 
  msg: ChatMessage;
  onPolicyClick?: (policyId: string) => void;
  onFeedback?: (msg: ChatMessage, type: 'positive' | 'negative') => void;
}) {
  const t = useTranslations('chat');
  const agentBadges = msg.role === 'assistant' ? detectAgentBadges(msg) : [];

  return (
    <div className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      {msg.role === 'assistant' && (
        <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0">
          <Bot className="w-5 h-5 text-indigo-600" />
        </div>
      )}
      <div
        className={`max-w-[85%] rounded-lg px-4 py-2 ${
          msg.role === 'user'
            ? 'bg-indigo-600 text-white'
            : 'bg-white text-slate-800 border border-slate-200 shadow-sm'
        }`}
      >
        {/* Agent badges — which tools/agents contributed */}
        {msg.role === 'assistant' && agentBadges.length > 0 && (
          <div className="flex flex-wrap items-center gap-1 mb-1.5 pb-1 border-b border-slate-100">
            {agentBadges.map((badge) => {
              const BadgeIcon = badge.icon;
              return (
                <span key={badge.label} className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium ${badge.color}`}>
                  <BadgeIcon className="w-2.5 h-2.5" />
                  {badge.label}
                </span>
              );
            })}
            {msg.agent?.framework && (
              <span className="text-[9px] text-slate-400 ml-auto">{msg.agent.name}</span>
            )}
          </div>
        )}

        <div className="text-sm">
          {msg.role === 'assistant' ? (
            <StructuredContentRenderer content={msg.content} onPolicyClick={onPolicyClick} />
          ) : (
            <span className="whitespace-pre-wrap">{msg.content}</span>
          )}
        </div>
        
        {/* Citations for assistant messages with RAG */}
        {msg.role === 'assistant' && msg.rag?.citations && (
          <PolicyCitations citations={msg.rag.citations} onPolicyClick={onPolicyClick} />
        )}

        {/* Policy PDF toolbox — quick links to referenced CG documents */}
        {msg.role === 'assistant' && (
          <PolicyToolbox content={msg.content} citations={msg.rag?.citations} />
        )}
        
        <div className={`flex items-center gap-1 text-xs mt-1 ${
          msg.role === 'user' ? 'text-indigo-200' : 'text-slate-400'
        }`}>
          <span>{msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          {msg.role === 'assistant' && msg.rag && <RAGStatsTooltip rag={msg.rag} />}
          {/* Feedback buttons for assistant messages */}
          {msg.role === 'assistant' && onFeedback && (
            <div className="flex items-center gap-1 ml-2">
              <button
                onClick={() => onFeedback(msg, 'positive')}
                disabled={msg.feedbackGiven != null}
                className={`p-0.5 rounded transition-colors ${
                  msg.feedbackGiven === 'positive'
                    ? 'text-emerald-500'
                    : msg.feedbackGiven != null
                      ? 'text-slate-300 cursor-not-allowed'
                      : 'text-slate-400 hover:text-emerald-500'
                }`}
                title={t('goodAnswer')}
              >
                <ThumbsUp className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => onFeedback(msg, 'negative')}
                disabled={msg.feedbackGiven != null}
                className={`p-0.5 rounded transition-colors ${
                  msg.feedbackGiven === 'negative'
                    ? 'text-rose-500'
                    : msg.feedbackGiven != null
                      ? 'text-slate-300 cursor-not-allowed'
                      : 'text-slate-400 hover:text-rose-500'
                }`}
                title={t('badAnswer')}
              >
                <ThumbsDown className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>
      {msg.role === 'user' && (
        <div className="w-8 h-8 rounded-lg bg-slate-200 flex items-center justify-center flex-shrink-0">
          <User className="w-5 h-5 text-slate-600" />
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent output formatting — convert raw JSON emitted by structured agents
// (DecisionAgent, PolicyAgent, etc.) into readable markdown so the chat UI
// looks consistent across all agents instead of dumping `{...}` blocks.
// ─────────────────────────────────────────────────────────────────────────────

const DECISION_LABELS: Record<string, string> = {
  documented_recommendation: 'Recommandation',
  recommendation: 'Recommandation',
  decision: 'Décision',
  rationale: 'Justifications',
  reasoning: 'Justifications',
  conditions_or_franchise: 'Conditions / Franchise',
  conditions: 'Conditions',
  next_steps: 'Prochaines étapes',
  actions: 'Actions',
  missing_items: 'Éléments manquants',
  missing_documents: 'Documents manquants',
  requires_human_review: 'Revue humaine requise',
  confidence: 'Confiance',
  risk_level: 'Niveau de risque',
  citations: 'Citations',
  sources: 'Sources',
};

function tryParseAgentJson(text: string): Record<string, unknown> | null {
  if (!text) return null;
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)```\s*$/i);
  const candidate = fenced ? fenced[1].trim() : trimmed;
  if (!(candidate.startsWith('{') && candidate.endsWith('}'))) return null;
  try {
    const parsed = JSON.parse(candidate);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function humanizeKey(key: string): string {
  return DECISION_LABELS[key]
    || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function renderAgentValue(value: unknown, indent = 0): string {
  if (value === null || value === undefined) return '_—_';
  if (typeof value === 'boolean') return value ? '✅ Oui' : '❌ Non';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) {
    if (value.length === 0) return '_(aucun)_';
    return value
      .map(v => {
        if (typeof v === 'string') return `${'  '.repeat(indent)}- ${v.trim()}`;
        if (v && typeof v === 'object') {
          const inner = Object.entries(v as Record<string, unknown>)
            .map(([k, val]) => `**${humanizeKey(k)}** : ${renderAgentValue(val, indent + 1)}`)
            .join(' · ');
          return `${'  '.repeat(indent)}- ${inner}`;
        }
        return `${'  '.repeat(indent)}- ${String(v)}`;
      })
      .join('\n');
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `- **${humanizeKey(k)}** : ${renderAgentValue(v, indent + 1)}`)
      .join('\n');
  }
  return String(value);
}

function formatAgentObject(obj: Record<string, unknown>): string | null {
  const keys = Object.keys(obj);
  const known = ['documented_recommendation', 'recommendation', 'decision', 'rationale', 'next_steps', 'missing_items', 'conditions_or_franchise', 'requires_human_review'];
  if (!keys.some(k => known.includes(k))) return null;

  const parts: string[] = [];
  const reco = (obj.documented_recommendation || obj.recommendation || obj.decision) as string | undefined;
  if (typeof reco === 'string' && reco) {
    const lower = reco.toLowerCase();
    const badge = lower.includes('approve') || lower.includes('accept') || lower === 'approuve' ? '🟢'
      : lower.includes('deny') || lower.includes('reject') || lower === 'refuse' ? '🔴'
      : lower.includes('review') ? '🟡'
      : '🔵';
    parts.push(`**${badge} ${humanizeKey('documented_recommendation')} :** \`${reco}\``);
  }

  const order = [
    'rationale', 'reasoning',
    'conditions_or_franchise', 'conditions',
    'missing_items', 'missing_documents',
    'next_steps', 'actions',
    'risk_level', 'confidence',
    'requires_human_review',
    'citations', 'sources',
  ];
  const skip = new Set(['documented_recommendation', 'recommendation', 'decision']);
  const remaining = [...order.filter(k => k in obj), ...keys.filter(k => !order.includes(k) && !skip.has(k))];

  for (const key of remaining) {
    if (skip.has(key)) continue;
    const val = obj[key];
    if (val === undefined) continue;
    if (Array.isArray(val) && val.length === 0) continue;
    parts.push(`\n**${humanizeKey(key)}**`);
    parts.push(renderAgentValue(val));
  }

  return parts.join('\n');
}

function formatAgentText(text: string): string {
  const parsed = tryParseAgentJson(text);
  if (!parsed) return text;
  const md = formatAgentObject(parsed);
  return md ?? text;
}

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
}: ChatDrawerProps) {
  const { addToast } = useToast();
  const t = useTranslations('chat');
  const locale = useLocale();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const requestGenerationRef = useRef(0);
  const { send: sendChatRequest, cancel: cancelChatRequest } = useConversationRequest(applicationId);
  const [loadingPhase, setLoadingPhase] = useState<LoadingPhase>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string>(t('newChat'));
  const [historyCollapsed, setHistoryCollapsed] = useState(true);
  const [useCorrections, setUseCorrections] = useState(true);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [workflowRunning, setWorkflowRunning] = useState<string | null>(null);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<string>('auto');
  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null);
  const [llmSuggestions, setLlmSuggestions] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const loadingPhaseTimerRef = useRef<NodeJS.Timeout | null>(null);

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

    type Rec = { id: string; score: number; reason: string };
    const recs: Rec[] = [];

    // Fraude workflow — high fraud indicators
    if (hasFraud || hasSIU) {
      recs.push({ id: 'fraude', score: hasSIU ? 95 : 80, reason: hasSIU ? t('recSIU') : t('recFraud') });
    }

    // Complet workflow — complex case
    if (isMajor || hasRecourse || hasExpertise || hasCatNat || (contextLabels && contextLabels.length > 3)) {
      const score = (isMajor ? 25 : 0) + (hasRecourse ? 20 : 0) + (hasExpertise ? 15 : 0) + (hasCatNat ? 15 : 0) + ((contextLabels?.length || 0) > 3 ? 10 : 0);
      recs.push({ id: 'complet', score: Math.min(90, 50 + score), reason: [
        isMajor && 'Sinistre majeur',
        hasRecourse && 'Recours tiers',
        hasExpertise && 'Expertise requise',
        hasCatNat && 'Cat-Nat',
      ].filter(Boolean).join(' + ') + ' — ' + t('recComplet') });
    }

    // Express workflow — routine/simple case
    if (!isMajor && !hasSIU && !hasCatNat && (contextLabels?.length || 0) <= 3) {
      recs.push({ id: 'express', score: hasFraud ? 40 : 70, reason: 'Express — ' + t('recComplet').replace('complète', 'express') });
    }

    // Also recommend specific agent pills based on context
    if (hasMissingDocs) recs.push({ id: 'agent:analysis', score: 60, reason: t('recMissing') });
    if (hasRecourse) recs.push({ id: 'agent:policy', score: 55, reason: t('recRecourse') });
    if (isMortgagePersona && hasMortgageRisk) {
      recs.push({ id: 'agent:analysis', score: 75, reason: 'Analyse HCSF recommandée' });
      recs.push({ id: 'complet', score: 70, reason: 'Dossier hypothécaire sensible — revue complète' });
    }
    if (isMortgagePersona && hasMortgageDocs) {
      recs.push({ id: 'agent:analysis', score: 68, reason: 'Pièces hypothécaires à compléter' });
    }

    return recs.sort((a, b) => b.score - a.score);
  }, [applicationStatus, contextLabels, contextTasks, persona, t]);

  const contextualSuggestions = useMemo(() => {
    // State-aware suggestions based on dossier lifecycle
    if (processingStatus === 'extracting') {
      return ['L\'extraction est en cours — les suggestions seront disponibles après l\'analyse'];
    }
    if (processingStatus === 'analyzing') {
      return ['L\'analyse IA est en cours — posez votre question, elle sera traitée après l\'analyse'];
    }
    if (applicationStatus === 'error') {
      return [
        'Le traitement a échoué — souhaitez-vous relancer l\'extraction ?',
        'Résume l\'erreur de traitement',
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
      suggestions.push('Résume la décision prise et les justifications');
      suggestions.push('Quels sont les prochains pas après cette décision ?');
    }

    // Generate suggestions from context labels (dossier-specific)
    if (contextLabels && contextLabels.length > 0) {
      const labelTypes = new Set(contextLabels.map(l => l.type));
      const labelKeys = new Set(contextLabels.map(l => l.key));

      if (labelKeys.has('convention_irsi')) suggestions.push('La convention IRSI s\'applique-t-elle à ce sinistre ?');
      if (labelKeys.has('garantie_dde')) suggestions.push('Quel est le montant de la franchise DDE applicable ?');
      if (labelKeys.has('garantie_tempete')) suggestions.push('La garantie tempête couvre-t-elle ces dommages ?');
      if (labelKeys.has('garantie_vol')) suggestions.push('Les conditions de la garantie vol sont-elles remplies ?');
      if (labelKeys.has('garantie_incendie')) suggestions.push('Quelles sont les exclusions de la garantie incendie ?');
      if (labelKeys.has('rc_habitation')) suggestions.push('Un recours contre le tiers est-il possible ?');
      if (labelKeys.has('regime_catnat')) suggestions.push('Y a-t-il eu un arrêté Cat-Nat pour cette commune et cette période ?');
      if (labelKeys.has('sinistre_majeur')) suggestions.push('Quels sont les seuils d\'expertise obligatoire selon les CG ?');
      if (labelTypes.has('fraud')) {
        suggestions.push('Quels sont les indicateurs de fraude détectés ?');
        suggestions.push('Analyse les photos pour vérifier l\'authenticité');
      }
      if (labelKeys.has('catnat_confirmee') || labelKeys.has('catnat_non_confirmee')) {
        suggestions.push('Quelles sont les conditions d\'indemnisation Cat-Nat ?');
      }
      if (labelKeys.has('exclusions_possibles')) suggestions.push('Quelles exclusions pourraient s\'appliquer à ce sinistre ?');
      if (labelKeys.has('couverture_non_confirmee')) suggestions.push('Ce sinistre est-il couvert par le contrat ?');

      if (labelKeys.has('hcsf_endettement_critique') || labelKeys.has('hcsf_endettement_tendu')) {
        suggestions.push('Le taux d\'endettement respecte-t-il les normes HCSF ?');
      }
      if (labelKeys.has('hcsf_ltv_critique') || labelKeys.has('hcsf_ltv_tendu')) {
        suggestions.push('Le ratio LTV est-il acceptable pour ce dossier ?');
      }
      if (labelKeys.has('hcsf_apport_faible')) {
        suggestions.push('L\'apport est-il suffisant pour respecter les exigences de souscription ?');
      }
      if (labelKeys.has('ptz')) {
        suggestions.push('Quelles conditions PTZ doivent être validées ?');
      }
      if (labelKeys.has('frontalier')) {
        suggestions.push('Quels justificatifs supplémentaires faut-il pour un dossier frontalier ?');
      }
      if (labelKeys.has('pieces_manquantes')) {
        suggestions.push('Liste les pièces manquantes et l\'ordre de priorité.');
      }
    }

    // Generate from context tasks
    if (contextTasks && contextTasks.length > 0) {
      for (const task of contextTasks) {
        if (task.category === 'coverage' && !suggestions.some(s => s.includes('couverture')))
          suggestions.push('Résume la couverture applicable selon les CG');
        else if (task.category === 'expertise' && !suggestions.some(s => s.includes('expertise')))
          suggestions.push('Quel type d\'expert faut-il mandater pour ce sinistre ?');
        else if (task.category === 'recourse')
          suggestions.push('Quelle est la procédure de recours tiers (IRSI / CIDE-COP) ?');
        else if (task.category === 'documents')
          suggestions.push('Quelles pièces manquent pour compléter ce dossier ?');
        else if (task.category === 'fraud' && !suggestions.some(s => s.includes('fraude')))
          suggestions.push('Résume l\'analyse anti-fraude de ce dossier');
        else if (task.category === 'verification')
          suggestions.push('Quelles vérifications réglementaires sont prioritaires sur ce dossier ?');
        else if (task.category === 'risk')
          suggestions.push('Quels signaux de risque justifient une revue approfondie ?');
      }
    }

    const unique = [...new Set(suggestions)];
    if (unique.length > 0) return unique;

    // Persona-based fallback (pre-analysis or non-claims personas)
    const fallback: Record<string, string[]> = {
      habitation_claims: [
        'Ce sinistre est-il couvert par les CG Habitation ?',
        'Quel est le montant de la franchise applicable ?',
        'Analyse les photos pour détecter une fraude',
      ],
      property_casualty_claims: [
        'Ce sinistre est-il couvert par les CG Habitation ?',
        'Quel est le montant de la franchise applicable ?',
      ],
      automotive_claims: [
        'Quelle est la responsabilité de l\'assuré ?',
        'Analyse les photos pour détecter une fraude',
      ],
      life_health_claims: [
        'Ce soin est-il pris en charge ?',
        'Quel est le taux de remboursement ?',
      ],
      underwriting: [
        'Quel est le niveau de risque cardiovasculaire ?',
        'Quelle formule recommander pour ce profil ?',
      ],
      mortgage: [
        'Le ratio LTV est-il acceptable ?',
        'Le taux d\'endettement est-il conforme ?',
        'Quelles normes HCSF posent le plus de risque sur ce dossier ?',
      ],
    };
    return fallback[persona] || fallback.habitation_claims || [];
  }, [persona, contextLabels, contextTasks, applicationStatus, processingStatus, hasDecision, activeAgent, llmSuggestions, t]);

  const stopLoadingPhases = useCallback(() => {
    if (loadingPhaseTimerRef.current) {
      clearTimeout(loadingPhaseTimerRef.current);
      loadingPhaseTimerRef.current = null;
    }
    setLoadingPhase(null);
  }, []);

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
      addToast('error', 'Impossible d\'envoyer le feedback');
    }
  }, [persona, conversationId, applicationId, addToast]);

  // Reset state when application changes
  useEffect(() => {
    requestGenerationRef.current += 1;
    cancelChatRequest();
    stopLoadingPhases();
    setMessages([]);
    setConversationId(null);
    setConversationTitle(t('newChat'));
    setIsLoading(false);
  }, [applicationId, t, cancelChatRequest, stopLoadingPhases]);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      requestGenerationRef.current += 1;
      if (loadingPhaseTimerRef.current) {
        clearTimeout(loadingPhaseTimerRef.current);
      }
    };
  }, []);

  // Load a specific conversation
  const loadConversation = useCallback(async (convId: string | null) => {
    const generation = ++requestGenerationRef.current;
    cancelChatRequest();
    setIsLoading(false);
    stopLoadingPhases();
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
        `/api/applications/${applicationId}/conversations/${convId}`
      );
      
      if (response.ok) {
        const data = await response.json();
        if (generation !== requestGenerationRef.current) return;
        setMessages(
          (data.messages || []).map((m: any) => ({
            ...m,
            timestamp: new Date(m.timestamp),
          }))
        );
        setConversationId(data.id);
        setConversationTitle(data.title || t('conversation'));
      }
    } catch (e) {
      if (generation !== requestGenerationRef.current) return;
      console.error('Failed to load conversation:', e);
      addToast('error', 'Impossible de charger la conversation');
    } finally {
      if (generation === requestGenerationRef.current) setIsLoadingConversation(false);
    }
  }, [applicationId, addToast, t, cancelChatRequest, stopLoadingPhases]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-activate Workflows pill when dossier finishes processing
  useEffect(() => {
    if (
      (applicationStatus === 'extracted' || applicationStatus === 'completed') &&
      messages.length === 0 &&
      activeAgent === 'auto'
    ) {
      setActiveAgent('workflow');
    }
  }, [applicationStatus, messages.length, activeAgent]);

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
    setWorkflowRunning(workflowId);

    // Start workflow-specific loading phases
    const phaseConfigs: Record<string, {key: string, delay: number}[]> = {
      express: [
        { key: 'workflowPhaseExtract', delay: 0 },
        { key: 'workflowPhaseDecision', delay: 8000 },
      ],
      complet: [
        { key: 'workflowPhaseExtract', delay: 0 },
        { key: 'workflowPhaseAnalysis', delay: 10000 },
        { key: 'workflowPhaseRisk', delay: 40000 },
      ],
      fraude: [
        { key: 'workflowPhaseFraud', delay: 0 },
        { key: 'workflowPhaseWebIntel', delay: 15000 },
        { key: 'workflowPhaseCrossCheck', delay: 35000 },
      ],
    };
    const phases = phaseConfigs[workflowId];
    if (phases) {
      setLoadingPhase('retrieving'); // initial
      const timers: ReturnType<typeof setTimeout>[] = [];
      phases.forEach((p, i) => {
        timers.push(setTimeout(() => setLoadingPhase(p.key as LoadingPhase), p.delay));
      });
      loadingPhaseTimerRef.current = timers[timers.length - 1];
    }

    // Add a system message showing workflow started
    const startMsg: ChatMessage = {
      role: 'assistant',
      content: `## 🚀 Workflow: ${workflowName}\n\n${t('workflowStarting', { name: workflowName })}`,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, startMsg]);

    try {
      const response = await fetch(
        `/api/applications/${applicationId}/workflow/${workflowId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ language: locale }),
        },
      );

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(err.detail || `Workflow failed: ${response.status}`);
      }

      const result = await response.json();

      // Build a rich response from workflow steps
      const parts: string[] = [`## ✅ ${t('workflowLabel')}: ${workflowName}\n`];
      if (result.steps && Array.isArray(result.steps)) {
        for (const step of result.steps) {
          parts.push(`### 🤖 ${step.agent}`);
          parts.push(formatAgentText(step.text));
          parts.push('');
        }
      }
      if (result.summary) {
        // Use blank lines around the summary so markdown headings (e.g. "### …")
        // inside `result.summary` are rendered as real headings instead of literal text.
        parts.push(`---\n\n**${t('workflowSummary')}**\n\n${formatAgentText(result.summary)}`);
      }
      parts.push(`\n_${t('workflowStatus')}: ${result.status || t('workflowCompletedStatus')}_`);

      const resultMsg: ChatMessage = {
        role: 'assistant',
        content: parts.join('\n'),
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, resultMsg]);
    } catch (err) {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: `## ❌ ${t('workflowErrorTitle')}\n\n${err instanceof Error ? err.message : t('unknownError')}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setWorkflowRunning(null);
      stopLoadingPhases();
    }
  }, [applicationId, isLoading, workflowRunning]);

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return;
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
      const data = await sendChatRequest({
        message: userMessage.content,
        conversation_id: conversationId,
        persona,
        agent_type: activeAgent,
        use_corrections: useCorrections,
        language: locale,
      });
      if (!data || generation !== requestGenerationRef.current) return;

      // Update conversation ID if this was a new conversation
      if (!conversationId && data.conversation_id) {
        setConversationId(data.conversation_id);
        setConversationTitle(data.title || t('newChat'));
        // Refresh the history panel
        if ((window as any).__refreshChatHistory) {
          (window as any).__refreshChatHistory();
        }
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
        stopLoadingPhases();
      }
    }
  }, [
    inputValue,
    isLoading,
    applicationId,
    conversationId,
    persona,
    activeAgent,
    useCorrections,
    t,
    addToast,
    stopLoadingPhases,
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
    stopLoadingPhases();
    setIsLoading(false);
    setIsLoadingConversation(false);
    setMessages([]);
    setConversationId(null);
    setConversationTitle(t('newChat'));
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleSelectConversation = (id: string | null, convApplicationId?: string) => {
    // If selecting a conversation from a different application, navigate to that application
    if (convApplicationId && convApplicationId !== applicationId) {
      // Navigate to the other application and open that conversation
      window.location.href = `/applications/${convApplicationId}?conversation=${id}`;
      return;
    }
    loadConversation(id);
  };

  return (
    <>
      {/* Floating Button - visible when drawer is closed */}
      <button
        onClick={onOpen}
        className={`fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-5 py-3 bg-indigo-600 text-white rounded-full shadow-lg hover:bg-indigo-700 hover:shadow-xl transition-all duration-300 group whitespace-nowrap ${
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
          <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center">
                <MessageSquare className="w-5 h-5 text-indigo-600" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-slate-900">
                  {conversationTitle}
                </h2>
                <p className="text-xs text-slate-500">
                  {conversationId ? t('messagesCount', { count: messages.length }) : t('startNewConversation')}
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              title={t('closeChat')}
              aria-label={t('closeChat')}
              className="p-2 hover:bg-slate-200 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-slate-500" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4" aria-busy={isLoading || isLoadingConversation}>
            {isLoadingConversation ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
              </div>
            ) : messages.length === 0 ? (
              <div className="text-center py-8">
                <Bot className="w-12 h-12 mx-auto mb-3 text-slate-300" />
                <p className="text-sm text-slate-500">
                  {t('emptyStateAsk')}
                </p>
                <div className="mt-4 space-y-2">
                  <p className="text-xs text-slate-400">{t('tryForExample')}</p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {contextualSuggestions.slice(0, 3).map((suggestion, idx) => (
                      <button
                        key={idx}
                        onClick={() => setInputValue(suggestion)}
                        className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-full transition-colors"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <MessageBubble key={idx} msg={msg} onPolicyClick={handlePolicyClick} onFeedback={handleFeedback} />
              ))
            )}
            
            {isLoading && <ChatMessageSkeleton />}

            {workflowRunning && (
              <div className="flex gap-3 justify-start">
                <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-5 h-5 text-violet-600" />
                </div>
                <div className="bg-violet-50 rounded-lg px-4 py-3 border border-violet-200 min-w-[240px]">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-violet-600 animate-spin" />
                    <div className="text-sm">
                      <span className="text-violet-700 font-medium animate-pulse">
                        {loadingPhase && loadingPhase.startsWith('workflow') ? t(loadingPhase) : t('workflowRunning')}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-1 mt-2">
                    {(workflowRunning === 'express' ? ['workflowPhaseExtract', 'workflowPhaseDecision'] :
                      workflowRunning === 'complet' ? ['workflowPhaseExtract', 'workflowPhaseAnalysis', 'workflowPhaseRisk'] :
                      ['workflowPhaseFraud', 'workflowPhaseWebIntel', 'workflowPhaseCrossCheck']
                    ).map((phase, i, arr) => {
                      const currentIdx = arr.indexOf(loadingPhase as string);
                      const thisIdx = i;
                      return (
                        <div key={phase} className={`h-1.5 rounded-full flex-1 transition-colors duration-700 ${
                          loadingPhase === phase ? 'bg-violet-500 animate-pulse' :
                          currentIdx > thisIdx ? 'bg-violet-300' : 'bg-violet-100'
                        }`} />
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-3 border-t border-slate-200 bg-white">
            {/* Agent pills + corrections toggle — single row */}
            <div className="flex items-center gap-1 mb-2">
              <div className="flex items-center gap-1 flex-1 overflow-x-auto">
              {([
                { id: 'auto', labelKey: 'agentAuto', descKey: 'agentAutoDesc', icon: Bot, activeClass: 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-300' },
                { id: 'data', labelKey: 'agentData', descKey: 'agentDataDesc', icon: Database, activeClass: 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300', fabric: true },
                { id: 'policy', labelKey: 'agentPolicy', descKey: 'agentPolicyDesc', icon: Shield, activeClass: 'bg-amber-100 text-amber-700 ring-1 ring-amber-300' },
                { id: 'analysis', labelKey: 'agentAnalysis', descKey: 'agentAnalysisDesc', icon: FileSearch, activeClass: 'bg-violet-100 text-violet-700 ring-1 ring-violet-300' },
                { id: 'dashboard', labelKey: 'agentDashboard', descKey: 'agentDashboardDesc', icon: BarChart3, activeClass: 'bg-cyan-100 text-cyan-700 ring-1 ring-cyan-300' },
                { id: 'workflow', labelKey: 'agentWorkflow', descKey: 'agentWorkflowDesc', icon: Workflow, activeClass: 'bg-fuchsia-100 text-fuchsia-700 ring-1 ring-fuchsia-300' },
              ] as const).map((agent) => {
                const Icon = agent.icon;
                const isActive = activeAgent === agent.id;
                const isFabric = 'fabric' in agent && agent.fabric;
                return (
                  <div key={agent.id} className="relative">
                  <button
                    onMouseEnter={() => setHoveredAgent(agent.id)}
                    onMouseLeave={() => setHoveredAgent(null)}
                    onClick={() => setActiveAgent(agent.id)}
                    className={`flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium transition-all whitespace-nowrap ${
                      isActive
                        ? agent.activeClass
                        : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                    }`}
                  >
                    {isFabric ? (
                      <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M8 1L14.5 5v6L8 15 1.5 11V5L8 1z" fill={isActive ? '#E8680C' : '#94a3b8'} opacity="0.85"/>
                        <path d="M8 1L14.5 5 8 9 1.5 5 8 1z" fill={isActive ? '#F59E0B' : '#cbd5e1'}/>
                      </svg>
                    ) : (
                      <Icon className="w-3 h-3" />
                    )}
                    {t(agent.labelKey)}
                    {isFabric && (
                      <span className={`ml-0.5 px-1 py-px rounded text-[8px] font-semibold leading-tight ${
                        isActive
                          ? 'bg-orange-200 text-orange-800'
                          : 'bg-slate-200 text-slate-500'
                      }`}>
                        Fabric
                      </span>
                    )}
                  </button>
                  {hoveredAgent === agent.id && (
                    <div className="absolute left-0 bottom-full mb-1.5 z-50 bg-slate-800 text-white text-[10px] rounded-lg shadow-lg px-3 py-2 min-w-[180px] max-w-[220px] pointer-events-none">
                      <div className="font-semibold mb-0.5">{t(agent.labelKey)}</div>
                      <div className="text-slate-300 leading-snug">{t(agent.descKey)}</div>
                      {isFabric && <div className="text-orange-300 mt-1 text-[9px]">Microsoft Fabric Data Agent — NL→SQL</div>}
                      <div className="absolute left-3 top-full w-2 h-2 bg-slate-800 transform rotate-45 -translate-y-1" />
                    </div>
                  )}
                  </div>
                );
              })}
              </div>
              {/* Corrections toggle — compact inline */}
              <div className="relative">
              <button
                onClick={() => setUseCorrections(prev => !prev)}
                onMouseEnter={() => setHoveredAgent('hitl')}
                onMouseLeave={() => setHoveredAgent(null)}
                title={t('correctionsToggle')}
                aria-label={t('correctionsToggle')}
                className={`flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium transition-all whitespace-nowrap flex-shrink-0 ${
                  useCorrections
                    ? 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300'
                    : 'bg-slate-100 text-slate-400'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${useCorrections ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                HITL
              </button>
              {hoveredAgent === 'hitl' && (
                <div className="absolute right-0 bottom-full mb-1.5 z-50 bg-slate-800 text-white text-[10px] rounded-lg shadow-lg px-3 py-2 min-w-[200px] max-w-[240px] pointer-events-none">
                  <div className="font-semibold mb-0.5">{t('correctionsTitle')}</div>
                  <div className="text-slate-300 leading-snug">
                    {useCorrections
                      ? t('correctionsOn')
                      : t('correctionsOff')}
                  </div>
                  <div className="absolute right-3 top-full w-2 h-2 bg-slate-800 transform rotate-45 -translate-y-1" />
                </div>
              )}
              </div>
            </div>
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
            {/* Contextual suggestion chips — always visible, derived from dossier context */}
            {contextualSuggestions.length > 0 && !isLoading && !workflowRunning && activeAgent !== 'workflow' && (
              <div className="flex gap-1.5 mb-2 overflow-x-auto pb-0.5 scrollbar-thin">
                {contextualSuggestions.slice(0, 4).map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setInputValue(suggestion);
                      inputRef.current?.focus();
                    }}
                    className="flex-shrink-0 text-[11px] px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-full transition-colors border border-indigo-100 hover:border-indigo-200 whitespace-nowrap"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
            {/* Workflow panel — visible when Workflows pill is active */}
            {activeAgent === 'workflow' && (applicationStatus === 'completed' || applicationStatus === 'extracted') && !isLoading && (
              <div className="mb-2 space-y-1.5">
                <div className="flex items-center gap-2 px-1">
                  <Workflow className="w-3.5 h-3.5 text-fuchsia-500" />
                  <span className="text-[11px] font-medium text-fuchsia-700">{t('workflowsTitle')}</span>
                </div>
                {/* Recommended workflow reason */}
                {recommendations.length > 0 && recommendations[0].id.startsWith('agent:') === false && (
                  <div className="px-2 py-1.5 bg-fuchsia-50 border border-fuchsia-100 rounded-lg">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-bold text-fuchsia-600 uppercase tracking-wide">{t('recommended')}</span>
                    </div>
                    <p className="text-[10px] text-fuchsia-700 mt-0.5">{recommendations[0].reason}</p>
                  </div>
                )}
                {(() => {
                  const workflows = [
                    {
                      id: 'express',
                      name: t('workflowExpressName'),
                      icon: '⚡',
                      pattern: t('workflowExpressPattern'),
                      duration: t('workflowExpressDuration'),
                      topClass: 'bg-emerald-100 border-emerald-300 text-emerald-900 ring-2 ring-emerald-200',
                      idleClass: 'bg-emerald-50 hover:bg-emerald-100 border-emerald-200 text-emerald-800 opacity-75',
                    },
                    {
                      id: 'complet',
                      name: t('workflowCompleteName'),
                      icon: '🔍',
                      pattern: t('workflowCompletePattern'),
                      duration: t('workflowCompleteDuration'),
                      topClass: 'bg-indigo-100 border-indigo-300 text-indigo-900 ring-2 ring-indigo-200',
                      idleClass: 'bg-indigo-50 hover:bg-indigo-100 border-indigo-200 text-indigo-800 opacity-75',
                    },
                    {
                      id: 'fraude',
                      name: t('workflowFraudName'),
                      icon: '🔎',
                      pattern: t('workflowFraudPattern'),
                      duration: t('workflowFraudDuration'),
                      topClass: 'bg-rose-100 border-rose-300 text-rose-900 ring-2 ring-rose-200',
                      idleClass: 'bg-rose-50 hover:bg-rose-100 border-rose-200 text-rose-800 opacity-75',
                    },
                  ] as const;
                  // Sort by recommendation score (recommended first)
                  const recMap = new Map(recommendations.filter(r => !r.id.startsWith('agent:')).map(r => [r.id, r]));
                  const sorted = [...workflows].sort((a, b) => (recMap.get(b.id)?.score || 0) - (recMap.get(a.id)?.score || 0));
                  return sorted.map((wf) => {
                    const rec = recMap.get(wf.id);
                    const isTop = rec && recommendations[0]?.id === wf.id;
                    return (
                      <button
                        key={wf.id}
                        onClick={() => handleWorkflow(wf.id, wf.name)}
                        disabled={!!workflowRunning}
                        className={`w-full text-left px-3 py-2 rounded-lg border transition-all disabled:opacity-50 hover:shadow-sm ${isTop ? wf.topClass : wf.idleClass}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-sm">{wf.icon}</span>
                            <span className="text-xs font-semibold">{wf.name}</span>
                            {isTop && <span className="text-[9px] px-1.5 py-0.5 bg-fuchsia-200 text-fuchsia-800 rounded-full font-bold">★ {t('recommended')}</span>}
                          </div>
                          <span className="text-[10px] text-slate-400">{wf.duration}</span>
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5 font-mono">{wf.pattern}</div>
                      </button>
                    );
                  });
                })()}
                {/* Agent pill recommendations */}
                {recommendations.filter(r => r.id.startsWith('agent:')).length > 0 && (
                  <div className="mt-1 pt-1.5 border-t border-slate-100">
                    <span className="text-[10px] text-slate-400 px-1">{t('suggestedAgents')}</span>
                    <div className="flex gap-1 mt-1">
                      {recommendations.filter(r => r.id.startsWith('agent:')).map(r => (
                        <button
                          key={r.id}
                          onClick={() => setActiveAgent(r.id.replace('agent:', ''))}
                          className="text-[10px] px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-full transition-colors"
                          title={r.reason}
                        >
                          {r.id === 'agent:policy' ? '🛡️ Polices' : r.id === 'agent:analysis' ? '🔍 Analyse' : r.id.replace('agent:', '')}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            {activeAgent === 'workflow' && applicationStatus !== 'completed' && applicationStatus !== 'extracted' && (
              <div className="mb-2 px-3 py-2 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-500 text-center">
                {t('workflowsRequireData')}
              </div>
            )}
            <div className="flex gap-2">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t(`placeholder${activeAgent === 'auto' ? 'Auto' : activeAgent === 'data' ? 'Data' : activeAgent === 'policy' ? 'Policy' : activeAgent === 'analysis' ? 'Analysis' : activeAgent === 'dashboard' ? 'Dashboard' : 'Workflow'}`)}
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
