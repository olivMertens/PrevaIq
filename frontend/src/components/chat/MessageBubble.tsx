'use client';

import { useState } from 'react';
import {
  Bot, User, Info, BookOpen, ChevronDown, ChevronUp, ExternalLink, ThumbsUp, ThumbsDown,
  Database, Shield, FileText, BarChart3, Globe,
} from 'lucide-react';
import { useTranslations, useLocale } from 'next-intl';
import { StructuredContentRenderer } from './ChatCards';
import WorkflowResult from './WorkflowResult';
import type { ChatMessage, RAGCitation, RAGMetadata } from './types';

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
                      <span className="capitalize">{citation.chunk_type === 'catalog_reference'
                        ? t('catalogReference') : citation.chunk_type}</span>
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
const TOOL_BADGES: Record<string, { labelKey: string; color: string; icon: typeof Bot }> = {
  search_policies: { labelKey: 'toolBadges.policies', color: 'bg-amber-100 text-amber-700', icon: Shield },
  get_application_summary: { labelKey: 'toolBadges.data', color: 'bg-emerald-100 text-emerald-700', icon: Database },
  get_glossary: { labelKey: 'toolBadges.glossary', color: 'bg-violet-100 text-violet-700', icon: BookOpen },
  query_fabric_data: { labelKey: 'toolBadges.fabric', color: 'bg-cyan-100 text-cyan-700', icon: BarChart3 },
  analyze_image_fraud: { labelKey: 'toolBadges.fraudDetection', color: 'bg-purple-100 text-purple-700', icon: Shield },
  web_search: { labelKey: 'toolBadges.webSearch', color: 'bg-blue-100 text-blue-700', icon: Globe },
  webiq_search: { labelKey: 'toolBadges.webIq', color: 'bg-blue-100 text-blue-700', icon: Globe },
};

// Detect which agents/tools contributed to a response
function detectAgentBadges(msg: ChatMessage, t: (key: string) => string): { label: string; color: string; icon: typeof Bot }[] {
  const badges: { label: string; color: string; icon: typeof Bot }[] = [];

  // From RAG citations
  if (msg.rag?.citations && msg.rag.citations.length > 0) {
    badges.push({ ...TOOL_BADGES.search_policies, label: t(TOOL_BADGES.search_policies.labelKey) });
  }

  for (const tool of msg.agent?.tools_called ?? []) {
    if (TOOL_BADGES[tool]) {
      badges.push({ ...TOOL_BADGES[tool], label: t(TOOL_BADGES[tool].labelKey) });
    }
  }

  // Deduplicate by label
  const seen = new Set<string>();
  return badges.filter(b => { if (seen.has(b.label)) return false; seen.add(b.label); return true; });
}

// Quick-link toolbox for policy PDFs referenced in message
function PolicyToolbox({ content, citations, t }: { content: string; citations?: RAGCitation[]; t: (key: string, values?: Record<string, string | number>) => string }) {
  // Collect policy IDs from inline references (e.g. PC-COV-001) and from RAG citations
  const policyIds = new Set<string>();
  const inlineMatches = content.match(/\b[A-Z]+-[A-Z]+-\d+\b/g);
  if (inlineMatches) inlineMatches.forEach(id => policyIds.add(id));
  if (citations) citations.forEach(c => policyIds.add(c.policy_id));

  if (policyIds.size === 0) return null;

  // Map policy ID prefixes to PDF filenames and labels
  const policyPdfMap: Record<string, { label: string; pdf: string }> = {
    'PC': { label: t('policyDocs.property'), pdf: 'habitation' },
    'LH': { label: t('policyDocs.health'), pdf: 'sante' },
    'AU': { label: t('policyDocs.auto'), pdf: 'auto' },
    'MO': { label: t('policyDocs.mortgage'), pdf: 'hypothecaire' },
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
          title={t('openPolicy', { label, references: ids.join(', ') })}
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
export default function MessageBubble({ 
  msg, 
  onPolicyClick,
  onFeedback,
}: { 
  msg: ChatMessage;
  onPolicyClick?: (policyId: string) => void;
  onFeedback?: (msg: ChatMessage, type: 'positive' | 'negative') => void;
}) {
  const t = useTranslations('chat');
  const locale = useLocale();
  const agentBadges = msg.role === 'assistant' ? detectAgentBadges(msg, t) : [];
  const citations = [...(msg.rag?.citations || []), ...(msg.policy_citations || [])];

  return (
    <div className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      {msg.role === 'assistant' && (
        <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0">
          <Bot className="w-5 h-5 text-indigo-600" />
        </div>
      )}
      <div
        className={`${msg.workflow ? 'min-w-0 flex-1' : 'max-w-[85%]'} rounded-lg px-4 py-2 ${
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
            msg.workflow ? (
              <WorkflowResult result={msg.workflow} onPolicyClick={onPolicyClick} />
            ) : (
              <StructuredContentRenderer content={msg.content} citations={citations} onPolicyClick={onPolicyClick} />
            )
          ) : (
            <span className="whitespace-pre-wrap">{msg.content}</span>
          )}
        </div>
        
        {/* Citations for assistant messages with RAG */}
        {msg.role === 'assistant' && citations.length > 0 && (
          <PolicyCitations citations={citations} onPolicyClick={onPolicyClick} />
        )}

        {/* Policy PDF toolbox — quick links to referenced CG documents */}
        {msg.role === 'assistant' && (
          <PolicyToolbox content={msg.content} citations={citations} t={t} />
        )}
        
        <div className={`flex items-center gap-1 text-xs mt-1 ${
          msg.role === 'user' ? 'text-indigo-200' : 'text-slate-400'
        }`}>
          <span>{msg.timestamp.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}</span>
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
