'use client';

import { 
  AlertTriangle, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  FileText, 
  TrendingUp, 
  TrendingDown,
  Minus,
  ThumbsUp,
  ThumbsDown,
  AlertCircle,
  ArrowRight,
  Shield,
  Activity,
  ExternalLink
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

// Type definitions for structured chat responses
export interface RiskFactor {
  title: string;
  description: string;
  risk_level: 'low' | 'moderate' | 'high';
  policy_id?: string;
}

export interface RiskFactorsResponse {
  type: 'risk_factors';
  summary: string;
  factors: RiskFactor[];
  overall_risk: 'low' | 'low-moderate' | 'moderate' | 'moderate-high' | 'high';
}

export interface PolicyItem {
  policy_id: string;
  name: string;
  relevance: string;
  finding: string;
}

export interface PolicyListResponse {
  type: 'policy_list';
  summary: string;
  policies: PolicyItem[];
}

export interface RecommendationResponse {
  type: 'recommendation';
  decision: 'approve' | 'approve_with_conditions' | 'defer' | 'decline';
  confidence: 'high' | 'medium' | 'low';
  summary: string;
  conditions?: string[];
  rationale: string;
  next_steps?: string[];
}

export interface ComparisonResponse {
  type: 'comparison';
  title: string;
  columns: string[];
  rows: { label: string; values: string[] }[];
}

export interface FraudAnalysisResponse {
  type: 'fraud_analysis';
  title: string;
  photosAnalyzed?: number;
  riskLevel?: string;
  score?: string;
  summary?: string;
  rationale?: string;
  findings: string[];
  consistency?: string;
}

export type StructuredResponse = 
  | RiskFactorsResponse 
  | PolicyListResponse 
  | RecommendationResponse 
  | ComparisonResponse
  | FraudAnalysisResponse;

// Risk level styling
const riskLevelConfig = {
  low: {
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    text: 'text-emerald-700',
    badge: 'bg-emerald-100 text-emerald-700',
    icon: CheckCircle2,
  },
  'low-moderate': {
    bg: 'bg-lime-50',
    border: 'border-lime-200',
    text: 'text-lime-700',
    badge: 'bg-lime-100 text-lime-700',
    icon: TrendingUp,
  },
  moderate: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-700',
    badge: 'bg-amber-100 text-amber-700',
    icon: AlertCircle,
  },
  'moderate-high': {
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    text: 'text-orange-700',
    badge: 'bg-orange-100 text-orange-700',
    icon: AlertTriangle,
  },
  high: {
    bg: 'bg-rose-50',
    border: 'border-rose-200',
    text: 'text-rose-700',
    badge: 'bg-rose-100 text-rose-700',
    icon: XCircle,
  },
};

// Decision styling (labels resolved at render time via i18n)
const decisionConfig = {
  approve: {
    bg: 'bg-emerald-50',
    border: 'border-emerald-300',
    text: 'text-emerald-800',
    icon: ThumbsUp,
    labelKey: 'approve' as const,
  },
  approve_with_conditions: {
    bg: 'bg-amber-50',
    border: 'border-amber-300',
    text: 'text-amber-800',
    icon: AlertCircle,
    labelKey: 'approveWithConditions' as const,
  },
  defer: {
    bg: 'bg-slate-50',
    border: 'border-slate-300',
    text: 'text-slate-800',
    icon: Clock,
    labelKey: 'defer' as const,
  },
  decline: {
    bg: 'bg-rose-50',
    border: 'border-rose-300',
    text: 'text-rose-800',
    icon: ThumbsDown,
    labelKey: 'decline' as const,
  },
};

// Risk Factors Card
export function RiskFactorsCard({ 
  data, 
  onPolicyClick 
}: { 
  data: RiskFactorsResponse;
  onPolicyClick?: (policyId: string) => void;
}) {
  const t = useTranslations('chatCards');
  const overallConfig = riskLevelConfig[data.overall_risk] || riskLevelConfig.moderate;
  const OverallIcon = overallConfig.icon;

  return (
    <div className="space-y-3">
      {/* Summary Header */}
      <div className={`${overallConfig.bg} ${overallConfig.border} border rounded-lg p-3`}>
        <div className="flex items-center gap-2 mb-1">
          <OverallIcon className={`w-5 h-5 ${overallConfig.text}`} />
          <span className={`text-sm font-semibold ${overallConfig.text}`}>
            {t('overallRisk')}: {data.overall_risk.replace('-', ' ').toUpperCase()}
          </span>
        </div>
        <p className="text-sm text-slate-600">{data.summary}</p>
      </div>

      {/* Factor Cards */}
      <div className="space-y-2">
        {data.factors.map((factor, idx) => {
          const config = riskLevelConfig[factor.risk_level] || riskLevelConfig.moderate;
          const Icon = config.icon;
          
          return (
            <div 
              key={idx} 
              className={`${config.bg} border ${config.border} rounded-lg p-3`}
            >
              <div className="flex items-start gap-3">
                <div className={`p-1.5 rounded-full ${config.badge}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-slate-800">{factor.title}</span>
                    {factor.policy_id && (
                      onPolicyClick ? (
                        <button
                          onClick={() => onPolicyClick(factor.policy_id!)}
                          className="flex items-center gap-1 text-xs font-mono bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded hover:bg-indigo-200 transition-colors cursor-pointer"
                          title={t('clickToViewPolicy')}
                        >
                          {factor.policy_id}
                          <ExternalLink className="w-3 h-3" />
                        </button>
                      ) : (
                        <span className="text-xs font-mono bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">
                          {factor.policy_id}
                        </span>
                      )
                    )}
                  </div>
                  <p className="text-xs text-slate-600 mt-1">{factor.description}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Policy List Card
export function PolicyListCard({ 
  data, 
  onPolicyClick 
}: { 
  data: PolicyListResponse;
  onPolicyClick?: (policyId: string) => void;
}) {
  const t = useTranslations('chatCards');
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">{data.summary}</p>
      
      <div className="space-y-2">
        {data.policies.map((policy, idx) => (
          onPolicyClick ? (
            <button
              key={idx}
              onClick={() => onPolicyClick(policy.policy_id)}
              className="w-full text-left bg-slate-50 border border-slate-200 rounded-lg p-3 hover:bg-indigo-50 hover:border-indigo-200 transition-colors cursor-pointer group"
              title={t('clickToViewFullPolicy')}
            >
              <div className="flex items-center gap-2 mb-2">
                <Shield className="w-4 h-4 text-indigo-600" />
                <span className="font-mono text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded">
                  {policy.policy_id}
                </span>
                <span className="font-medium text-sm text-slate-800 flex-1">{policy.name}</span>
                <ExternalLink className="w-4 h-4 text-slate-400 group-hover:text-indigo-600 transition-colors" />
              </div>
              <div className="pl-6 space-y-1">
                <p className="text-xs text-slate-500">
                  <span className="font-medium">{t('relevance')}:</span> {policy.relevance}
                </p>
                <p className="text-xs text-slate-700">
                  <span className="font-medium">{t('finding')}:</span> {policy.finding}
                </p>
              </div>
            </button>
          ) : (
            <div 
              key={idx}
              className="bg-slate-50 border border-slate-200 rounded-lg p-3"
            >
              <div className="flex items-center gap-2 mb-2">
                <Shield className="w-4 h-4 text-indigo-600" />
                <span className="font-mono text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded">
                  {policy.policy_id}
                </span>
                <span className="font-medium text-sm text-slate-800">{policy.name}</span>
              </div>
              <div className="pl-6 space-y-1">
                <p className="text-xs text-slate-500">
                  <span className="font-medium">{t('relevance')}:</span> {policy.relevance}
                </p>
                <p className="text-xs text-slate-700">
                  <span className="font-medium">{t('finding')}:</span> {policy.finding}
                </p>
              </div>
            </div>
          )
        ))}
      </div>
    </div>
  );
}

// Recommendation Card
export function RecommendationCard({ data }: { data: RecommendationResponse }) {
  const t = useTranslations('chatCards');
  const config = decisionConfig[data.decision] || decisionConfig.defer;
  const DecisionIcon = config.icon;

  return (
    <div className="space-y-3">
      {/* Decision Banner */}
      <div className={`${config.bg} border-2 ${config.border} rounded-lg p-4`}>
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-full ${config.bg}`}>
            <DecisionIcon className={`w-6 h-6 ${config.text}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className={`text-lg font-bold ${config.text}`}>
                {t(config.labelKey)}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                data.confidence === 'high' ? 'bg-emerald-100 text-emerald-700' :
                data.confidence === 'medium' ? 'bg-amber-100 text-amber-700' :
                'bg-slate-100 text-slate-600'
              }`}>
                {t('confidenceLevel', { level: t(`confidence_${data.confidence}`) })}
              </span>
            </div>
            <p className="text-sm text-slate-600 mt-1">{data.summary}</p>
          </div>
        </div>
      </div>

      {/* Conditions */}
      {data.conditions && data.conditions.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-4 h-4 text-amber-600" />
            <span className="text-sm font-medium text-amber-800">{t('conditions')}</span>
          </div>
          <ul className="space-y-1 pl-6">
            {data.conditions.map((condition, idx) => (
              <li key={idx} className="text-sm text-amber-700 list-disc">{condition}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Rationale */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
        <div className="flex items-center gap-2 mb-2">
          <FileText className="w-4 h-4 text-slate-600" />
          <span className="text-sm font-medium text-slate-700">{t('rationale')}</span>
        </div>
        <p className="text-sm text-slate-600 pl-6">{data.rationale}</p>
      </div>

      {/* Next Steps */}
      {data.next_steps && data.next_steps.length > 0 && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <ArrowRight className="w-4 h-4 text-indigo-600" />
            <span className="text-sm font-medium text-indigo-700">{t('nextSteps')}</span>
          </div>
          <ul className="space-y-1 pl-6">
            {data.next_steps.map((step, idx) => (
              <li key={idx} className="text-sm text-indigo-600 list-disc">{step}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Comparison Table Card
export function ComparisonCard({ data }: { data: ComparisonResponse }) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium text-slate-800">{data.title}</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-slate-100">
              <th className="text-left p-2 border border-slate-200 font-medium text-slate-700"></th>
              {data.columns.map((col, idx) => (
                <th key={idx} className="text-left p-2 border border-slate-200 font-medium text-slate-700">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, idx) => (
              <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
                <td className="p-2 border border-slate-200 font-medium text-slate-700">{row.label}</td>
                {row.values.map((val, vidx) => (
                  <td key={vidx} className="p-2 border border-slate-200 text-slate-600">{val}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function FraudAnalysisCard({ data }: { data: FraudAnalysisResponse }) {
  const t = useTranslations('chatCards');
  const level = (data.riskLevel || '').toLowerCase();
  const levelConfig = level.includes('high') || level.includes('élev')
    ? riskLevelConfig.high
    : level.includes('moderate') || level.includes('mod')
      ? riskLevelConfig.moderate
      : riskLevelConfig.low;
  const LevelIcon = levelConfig.icon;

  return (
    <div className="space-y-3">
      <div className={`${levelConfig.bg} ${levelConfig.border} border rounded-lg p-4`}>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <LevelIcon className={`w-5 h-5 ${levelConfig.text}`} />
              <span className={`text-sm font-semibold ${levelConfig.text}`}>{data.title}</span>
            </div>
            {data.summary && <p className="text-sm text-slate-700 leading-relaxed">{data.summary}</p>}
          </div>
          <div className="flex gap-2 flex-wrap">
            {typeof data.photosAnalyzed === 'number' && (
              <span className="px-2 py-1 rounded-full bg-white/80 text-xs font-medium text-slate-700 border border-slate-200">
                {t('photosAnalyzed')}: {data.photosAnalyzed}
              </span>
            )}
            {data.score && (
              <span className="px-2 py-1 rounded-full bg-white/80 text-xs font-medium text-slate-700 border border-slate-200">
                {t('score')}: {data.score}
              </span>
            )}
            {data.riskLevel && (
              <span className={`px-2 py-1 rounded-full text-xs font-medium ${levelConfig.badge}`}>
                {t('riskLevel')}: {data.riskLevel}
              </span>
            )}
          </div>
        </div>
      </div>

      {data.rationale && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="w-4 h-4 text-slate-600" />
            <span className="text-sm font-medium text-slate-700">{t('rationale')}</span>
          </div>
          <p className="text-sm text-slate-600">{data.rationale}</p>
        </div>
      )}

      {data.findings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span className="text-sm font-medium text-amber-800">{t('findings')}</span>
          </div>
          <ul className="space-y-1.5">
            {data.findings.map((finding, idx) => (
              <li key={idx} className="text-sm text-amber-900 leading-relaxed">
                {typeof finding === 'string' ? finding : String((finding as any).summary || (finding as any).title || JSON.stringify(finding))}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.consistency && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-indigo-600" />
            <span className="text-sm font-medium text-indigo-700">{t('consistency')}</span>
          </div>
          <p className="text-sm text-indigo-700">{data.consistency}</p>
        </div>
      )}
    </div>
  );
}

function parseFraudMarkdown(content: string): FraudAnalysisResponse | null {
  if (!content.includes('## Analyse fraude photo')) {
    return null;
  }

  const lines = content.split('\n').map(line => line.trimEnd());
  const findings: string[] = [];
  let photosAnalyzed: number | undefined;
  let riskLevel: string | undefined;
  let score: string | undefined;
  let summary: string | undefined;
  let rationale: string | undefined;
  let consistency: string | undefined;
  let inFindings = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line === '## Analyse fraude photo') {
      continue;
    }
    if (line.startsWith('Points relevés')) {
      inFindings = true;
      continue;
    }
    if (line.startsWith('Cohérence déclaration/photos')) {
      inFindings = false;
      consistency = line.split(':').slice(1).join(':').trim();
      continue;
    }
    if (line.startsWith('- Photos analysées')) {
      const value = line.split(':').slice(1).join(':').trim();
      const parsed = Number(value);
      photosAnalyzed = Number.isFinite(parsed) ? parsed : undefined;
      continue;
    }
    if (line.startsWith('- Niveau de risque')) {
      riskLevel = line.split(':').slice(1).join(':').trim();
      continue;
    }
    if (line.startsWith('- Score')) {
      score = line.split(':').slice(1).join(':').trim();
      continue;
    }
    if (line.startsWith('Synthèse')) {
      summary = line.split(':').slice(1).join(':').trim();
      continue;
    }
    if (line.startsWith('Justification')) {
      rationale = line.split(':').slice(1).join(':').trim();
      continue;
    }
    if (inFindings && (line.startsWith('- ') || line.startsWith('• '))) {
      findings.push(line.replace(/^[-•]\s*/, ''));
      continue;
    }
    if (inFindings && line.startsWith('  - ')) {
      findings.push(line.replace(/^\s*-\s*/, ''));
    }
  }

  return {
    type: 'fraud_analysis',
    title: 'Analyse fraude photo',
    photosAnalyzed,
    riskLevel,
    score,
    summary,
    rationale,
    findings,
    consistency,
  };
}

// Parse JSON from content (handles ```json blocks)
export function parseStructuredContent(content: string): { structured: StructuredResponse | null; plainText: string } {
  // Look for JSON code blocks
  const jsonMatch = content.match(/```json\s*([\s\S]*?)```/);
  
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[1].trim());
      if (parsed.type && ['risk_factors', 'policy_list', 'recommendation', 'comparison', 'fraud_analysis'].includes(parsed.type)) {
        // Extract any text before/after the JSON block
        const beforeJson = content.slice(0, jsonMatch.index).trim();
        const afterJson = content.slice((jsonMatch.index || 0) + jsonMatch[0].length).trim();
        const plainText = [beforeJson, afterJson].filter(Boolean).join('\n\n');
        
        return { structured: parsed as StructuredResponse, plainText };
      }
    } catch (e) {
      // JSON parse failed, return as plain text
      console.debug('Failed to parse JSON in chat response:', e);
    }
  }

  const fraudStructured = parseFraudMarkdown(content);
  if (fraudStructured) {
    return { structured: fraudStructured, plainText: '' };
  }
  
  return { structured: null, plainText: content };
}

// Markdown components with Tailwind styling for chat messages
const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="text-base font-bold text-slate-900 mt-3 mb-1.5 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="text-sm font-bold text-slate-800 mt-3 mb-1 first:mt-0 border-b border-slate-200 pb-0.5">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold text-slate-800 mt-2 mb-1 first:mt-0">{children}</h3>,
  h4: ({ children }) => <h4 className="text-xs font-semibold text-slate-700 mt-2 mb-0.5 first:mt-0">{children}</h4>,
  p: ({ children }) => <p className="text-sm text-slate-700 mb-1.5 last:mb-0 leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  em: ({ children }) => <em className="italic text-slate-600">{children}</em>,
  ul: ({ children }) => <ul className="list-disc list-outside ml-4 mb-1.5 space-y-0.5 text-sm">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-outside ml-4 mb-1.5 space-y-0.5 text-sm">{children}</ol>,
  li: ({ children }) => <li className="text-slate-700 leading-relaxed">{children}</li>,
  hr: () => <hr className="my-2 border-slate-200" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-3 border-indigo-300 pl-3 my-1.5 text-sm italic text-slate-600 bg-indigo-50/50 py-1 rounded-r">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-2 rounded border border-slate-200">
      <table className="min-w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-100">{children}</thead>,
  th: ({ children }) => <th className="px-2 py-1.5 text-left font-semibold text-slate-700 border-b border-slate-200">{children}</th>,
  td: ({ children }) => <td className="px-2 py-1 text-slate-600 border-b border-slate-100">{children}</td>,
  code: ({ className, children }) => {
    const isInline = !className;
    if (isInline) {
      return (
        <code className="font-mono text-xs bg-indigo-100 text-indigo-700 px-1 py-0.5 rounded">
          {children}
        </code>
      );
    }
    return (
      <code className={`block overflow-x-auto p-2 text-xs bg-slate-50 rounded border border-slate-200 ${className || ''}`}>
        {children}
      </code>
    );
  },
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-600 underline hover:text-indigo-800 inline-flex items-center gap-0.5">
      {children}<ExternalLink className="w-3 h-3 inline" />
    </a>
  ),
};

// Render markdown content — used for assistant messages
function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {content}
    </ReactMarkdown>
  );
}

// Main renderer component
export function StructuredContentRenderer({ 
  content, 
  onPolicyClick 
}: { 
  content: string;
  onPolicyClick?: (policyId: string) => void;
}) {
  const { structured, plainText } = parseStructuredContent(content);
  
  return (
    <div className="space-y-3">
      {/* Render plain text as rich markdown */}
      {plainText && (
        <div className="text-sm chat-markdown">
          <MarkdownRenderer content={plainText} />
        </div>
      )}
      
      {/* Render structured content */}
      {structured && (
        <div className="mt-2">
          {structured.type === 'risk_factors' && <RiskFactorsCard data={structured} onPolicyClick={onPolicyClick} />}
          {structured.type === 'policy_list' && <PolicyListCard data={structured} onPolicyClick={onPolicyClick} />}
          {structured.type === 'recommendation' && <RecommendationCard data={structured} />}
          {structured.type === 'comparison' && <ComparisonCard data={structured} />}
          {structured.type === 'fraud_analysis' && <FraudAnalysisCard data={structured} />}
        </div>
      )}
    </div>
  );
}
