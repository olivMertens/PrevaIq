import type { CaseView } from './caseUrl';
import type { DeepDiveTab } from '@/components/case/caseSignals';
import type { ApplicationMetadata } from './types';
import type { FraudAnalysisResponse } from './api';

export const CLAIM_VIEWS = ['overview', 'documents', 'analysis', 'customer', 'weather', 'timeline'] as const;
export const ANALYSIS_SECTIONS = ['summary', 'cover', 'fraud', 'web'] as const;

export function claimViewForDetail(tab: DeepDiveTab): CaseView {
  switch (tab) {
    case 'summary':
    case 'cover':
    case 'fraud':
    case 'web':
      return 'analysis';
    case 'evidence':
      return 'documents';
    case 'customer':
    case 'timeline':
    case 'data':
    case 'pipeline':
      return tab;
  }
}

export function isClaimsWorkspace(persona: string): boolean {
  return ['habitation_claims', 'property_casualty_claims', 'automotive_claims'].includes(persona);
}

export function claimCommunicationStatus(application: ApplicationMetadata | null): 'approved' | 'pending' | 'denied' {
  const recorded: unknown = application?.llm_outputs?.decision;
  if (!recorded || typeof recorded !== 'object' || !('decision' in recorded)) return 'pending';
  return recorded.decision === 'approve' ? 'approved' : recorded.decision === 'decline' ? 'denied' : 'pending';
}

function isSavedFraud(value: unknown): value is FraudAnalysisResponse {
  return typeof value === 'object' && value !== null &&
    'overall_assessment' in value && typeof value.overall_assessment === 'object' && value.overall_assessment !== null &&
    'image_analyses' in value && Array.isArray(value.image_analyses) &&
    'application_id' in value && typeof value.application_id === 'string' &&
    'analysis_timestamp' in value && typeof value.analysis_timestamp === 'string';
}

export function savedClaimFraud(application: ApplicationMetadata | null): FraudAnalysisResponse | null {
  const saved = application?.fraud_analysis;
  return isSavedFraud(saved) ? saved : null;
}
