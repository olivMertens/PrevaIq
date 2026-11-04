// Health of the AI pipeline that read a case: quiet when fine, loud only when abnormal.
// Pure module (no imports) so tests can load it without the Next.js toolchain.

export type PipelineHealthStatus = 'ok' | 'review' | 'problem';

export interface PipelineHealthSource {
  processing_error?: string | null;
  extraction_provenance?: {
    review_required?: boolean;
    summary?: { fallback_used?: boolean; fallback_reason?: string | null } | null;
  } | null;
  orchestration?: {
    stages?: Record<string, { budget_exhausted?: boolean } | null> | null;
    review?: { status?: string | null; reasons?: Array<{ code: string }> | null } | null;
  } | null;
}

export interface PipelineHealth {
  status: PipelineHealthStatus;
  /** Review reason codes, problems first (translated by the caller). */
  reasons: string[];
  fallbackReason: string | null;
}

const PROBLEM_CODES = new Set([
  'no_content',
  'analysis_errors',
  'extraction_budget_exhausted',
  'analysis_budget_exhausted',
]);

export function pipelineHealth(source: PipelineHealthSource): PipelineHealth {
  const review = source.orchestration?.review;
  const codes = (review?.reasons ?? []).map((reason) => reason.code).filter(Boolean);
  const reasons = [
    ...codes.filter((code) => PROBLEM_CODES.has(code)),
    ...codes.filter((code) => !PROBLEM_CODES.has(code)),
  ];
  const summary = source.extraction_provenance?.summary;
  const fallbackReason = summary?.fallback_used ? summary.fallback_reason || 'fallback' : null;
  const budgetExhausted = Object.values(source.orchestration?.stages ?? {}).some(
    (stage) => stage?.budget_exhausted,
  );

  if (source.processing_error || budgetExhausted || reasons.some((code) => PROBLEM_CODES.has(code))) {
    return { status: 'problem', reasons, fallbackReason };
  }
  if (review?.status === 'reviewed') return { status: 'ok', reasons: [], fallbackReason: null };
  // A fallback engine still read the case: worth a look, not an alarm.
  if (fallbackReason || review?.status === 'needs_review' || source.extraction_provenance?.review_required) {
    return { status: 'review', reasons, fallbackReason };
  }
  return { status: 'ok', reasons, fallbackReason: null };
}
