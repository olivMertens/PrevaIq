import type { ApplicationListItem, PromptsData, AnalyzerStatus, AnalyzerInfo, FieldSchema, UnderwritingPolicy, PolicyCriteriaItem } from '@/lib/types';
import type { IndexStats } from '@/lib/api';

export type ProcessingStep = 'idle' | 'uploading' | 'extracting' | 'analyzing' | 'complete' | 'error';
export type AdminTab = 'documents' | 'prompts' | 'policies' | 'analyzer' | 'glossary';

export interface ProcessingState {
  step: ProcessingStep;
  message: string;
  appId?: string;
}

// Re-export types used by sub-components
export type {
  ApplicationListItem,
  PromptsData,
  AnalyzerStatus,
  AnalyzerInfo,
  FieldSchema,
  UnderwritingPolicy,
  PolicyCriteriaItem,
  IndexStats,
};
