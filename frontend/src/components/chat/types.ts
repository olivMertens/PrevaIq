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
