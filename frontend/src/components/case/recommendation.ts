// Recommended next decision for a claim, with its reason (no invented confidence score).
// Pure module (no imports) so tests can load it without the Next.js toolchain.

export type DecisionValue = 'approve' | 'approve_with_conditions' | 'defer' | 'decline';

export type RecommendationId =
  | 'escalate_siu'
  | 'request_expertise'
  | 'approve_with_expertise'
  | 'stp_approve'
  | 'approve_standard';

export type RecommendationTone = 'critical' | 'warning' | 'success';

export interface RecommendationOption {
  id: string;
  title: string;
  reason: string;
  decision: DecisionValue;
}

export interface Recommendation extends RecommendationOption {
  id: RecommendationId;
  tone: RecommendationTone;
  /** Backend context task that carries out this recommendation, highlighted in "Next steps". */
  taskKey?: string;
  alternatives: RecommendationOption[];
}

export interface RecommendationInput {
  analysisComplete: boolean;
  fraudRisk: number;
  siuRecommended: boolean;
  inconsistentStatement: boolean;
  amount: number;
  /** Amount and threshold already formatted with the claim currency and UI locale. */
  amountLabel: string;
  thresholdLabel: string;
}

type Translate = (key: string, values?: Record<string, string | number>) => string;

// Same thresholds as the previous next-best-action rules; each maps to a real decision type.
export function buildRecommendation(input: RecommendationInput, t: Translate): Recommendation | null {
  if (!input.analysisComplete) return null;
  const option = (
    id: string,
    decision: DecisionValue,
    values?: Record<string, string | number>,
    reasonKey: string = id,
  ): RecommendationOption => ({
    id,
    decision,
    title: t(`labels.${id}`),
    reason: t(`reasoning.${reasonKey}`, values),
  });

  if (input.siuRecommended) {
    return {
      ...option('escalate_siu', 'defer', undefined, 'siu_default'),
      id: 'escalate_siu',
      tone: 'critical',
      taskKey: 'siu_referral',
      alternatives: [option('request_docs', 'defer'), option('call_client', 'defer')],
    };
  }
  if (input.fraudRisk > 0.6 || input.inconsistentStatement) {
    return {
      ...option('request_expertise', 'defer', { percent: Math.round(input.fraudRisk * 100) }),
      id: 'request_expertise',
      tone: 'warning',
      taskKey: 'mandate_expert',
      alternatives: [option('approve_partial', 'approve_with_conditions'), option('escalate_manager', 'defer')],
    };
  }
  if (input.amount > 5000 && input.fraudRisk < 0.3) {
    return {
      ...option('approve_with_expertise', 'approve_with_conditions', {
        amount: input.amountLabel,
        threshold: input.thresholdLabel,
      }),
      id: 'approve_with_expertise',
      tone: 'warning',
      taskKey: 'mandate_expert',
      alternatives: [option('approve_direct', 'approve')],
    };
  }
  if (input.fraudRisk < 0.3 && input.amount <= 5000) {
    return {
      ...option('stp_approve', 'approve', { amount: input.amountLabel }),
      id: 'stp_approve',
      tone: 'success',
      alternatives: [option('manual_review', 'defer')],
    };
  }
  return {
    ...option('approve_standard', 'approve'),
    id: 'approve_standard',
    tone: 'success',
    alternatives: [option('request_info', 'defer')],
  };
}
