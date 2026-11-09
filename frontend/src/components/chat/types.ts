// Shared types of the Ask IQ chat panel.

export interface RAGCitation {
  policy_id: string;
  policy_name: string;
  chunk_type: string;
  criteria_id?: string;
}

export interface RAGMetadata {
  enabled: boolean;
  chunks_retrieved?: number;
  tokens_used?: number;
  latency_ms?: number;
  citations?: RAGCitation[];
  inferred_categories?: string[];
  fallback?: boolean;
  fallback_reason?: string;
}

export interface AgentMetadata {
  name: string;
  tools_available?: string[];
  tools_called?: string[];
  framework?: string;
}

export type WorkflowStepStatus = 'waiting' | 'running' | 'completed' | 'needs_review' | 'failed';

export interface WorkflowStage {
  id: 'context' | 'parallel' | 'synthesis';
  agents: string[];
}

export interface WorkflowExecution {
  plan: WorkflowStage[];
  context: WorkflowStepStatus;
  agents: Record<string, { status: WorkflowStepStatus; duration_ms?: number }>;
}

export type WorkflowEvent =
  | { type: 'plan'; plan: WorkflowStage[] }
  | { type: 'stage'; id: 'context'; status: WorkflowStepStatus }
  | { type: 'step'; agent: string; status: WorkflowStepStatus; duration_ms?: number };

export interface WorkflowResponse {
  workflow: string;
  status: 'completed' | 'needs_review';
  steps: { agent: string; text: string }[];
  summary: string;
  plan?: WorkflowStage[];
}

export interface WorkflowRunResult {
  /** express | complet | fraude */
  id: string;
  /** Localized workflow name */
  name: string;
  /** completed | needs_review */
  status: string;
  steps: { agent: string; text: string }[];
  /** Output of the synthesizing agent (the last step) */
  summary: string;
  durationMs: number;
  execution?: WorkflowExecution;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  rag?: RAGMetadata;
  agent?: AgentMetadata;
  workflow?: WorkflowRunResult;
  feedbackGiven?: 'positive' | 'negative' | null;
  /** The user query this assistant message responds to */
  userQuery?: string;
}

export type ChatMode = 'auto' | 'data' | 'policy' | 'analysis' | 'dashboard' | 'workflow';

export interface ChatRecommendation {
  /** A workflow id, or "agent:<mode>" for a chat mode */
  id: string;
  score: number;
  reason: string;
}

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
