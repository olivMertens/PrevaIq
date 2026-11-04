// "Latest updates" for a case, built only from timestamps the API already returns.
// Pure module (no imports) so tests can load it without the Next.js toolchain.

export type UpdateKind =
  | 'created'
  | 'extraction'
  | 'analysis'
  | 'sentiment'
  | 'fraud'
  | 'webCheck'
  | 'decision'
  | 'action';

export interface CaseUpdate {
  id: string;
  kind: UpdateKind;
  /** Epoch milliseconds. */
  at: number;
  params: Record<string, string | number>;
  /** Free-text label for history entries that carry their own wording. */
  label?: string;
}

export interface CaseUpdateSource {
  created_at?: string | null;
  files?: unknown[] | null;
  extracted_fields?: Record<string, unknown> | null;
  orchestration?: {
    stages?: Record<string, { completed_at?: string | null } | null> | null;
    review?: { status?: string | null } | null;
  } | null;
  sentiment_analysis?: { computed_at?: string | null; level?: string | null; score?: number | null } | null;
  fraud_analysis?: {
    analysis_timestamp?: string | null;
    overall_assessment?: {
      overall_fraud_risk?: string | null;
      risk_score?: number | null;
      siu_referral_recommended?: boolean | null;
    } | null;
    web_intelligence?: {
      event_verified?: boolean | null;
      source_urls?: string[] | null;
      skipped?: string | null;
      error?: string | null;
    } | null;
  } | null;
  action_history?: Array<{ action_id?: string; label?: string; at?: string; decision?: string | null }> | null;
}

function toEpoch(value: string | null | undefined): number | null {
  if (!value) return null;
  const at = Date.parse(value);
  return Number.isNaN(at) ? null : at;
}

/** Most recent first. */
export function collectCaseUpdates(source: CaseUpdateSource): CaseUpdate[] {
  const updates: CaseUpdate[] = [];
  const push = (update: Omit<CaseUpdate, 'at'>, timestamp: string | null | undefined) => {
    const at = toEpoch(timestamp);
    if (at !== null) updates.push({ ...update, at });
  };

  const files = source.files?.length ?? 0;
  const fields = Object.keys(source.extracted_fields ?? {}).length;
  push({ id: 'created', kind: 'created', params: { files } }, source.created_at);

  const stages = source.orchestration?.stages ?? {};
  push({ id: 'extraction', kind: 'extraction', params: { files, fields } }, stages.extraction?.completed_at);
  push(
    {
      id: 'analysis',
      kind: 'analysis',
      params: { review: source.orchestration?.review?.status === 'needs_review' ? 1 : 0 },
    },
    stages.analysis?.completed_at,
  );

  const sentiment = source.sentiment_analysis;
  if (sentiment?.level) {
    push(
      { id: 'sentiment', kind: 'sentiment', params: { level: sentiment.level, score: sentiment.score ?? 0 } },
      sentiment.computed_at,
    );
  }

  const fraud = source.fraud_analysis;
  if (fraud?.analysis_timestamp) {
    const assessment = fraud.overall_assessment;
    push(
      {
        id: 'fraud',
        kind: 'fraud',
        params: {
          band: assessment?.overall_fraud_risk || 'LOW',
          score: Math.round((assessment?.risk_score ?? 0) * 100),
          siu: assessment?.siu_referral_recommended ? 1 : 0,
        },
      },
      fraud.analysis_timestamp,
    );
    const web = fraud.web_intelligence;
    if (web && !web.error) {
      const verdict = web.skipped ? 'skipped' : web.event_verified === true ? 'confirmed' : web.event_verified === false ? 'notConfirmed' : 'unclear';
      push(
        { id: 'webCheck', kind: 'webCheck', params: { verdict, sources: web.source_urls?.length ?? 0 } },
        fraud.analysis_timestamp,
      );
    }
  }

  (source.action_history ?? []).forEach((entry, index) => {
    push(
      {
        id: entry.action_id || `action-${index}`,
        kind: entry.decision ? 'decision' : 'action',
        params: entry.decision ? { decision: entry.decision } : {},
        label: entry.label,
      },
      entry.at,
    );
  });

  // Same instant: keep the analysis order (fraud before its web check).
  const order: UpdateKind[] = ['decision', 'action', 'fraud', 'webCheck', 'sentiment', 'analysis', 'extraction', 'created'];
  return updates.sort((a, b) => b.at - a.at || order.indexOf(a.kind) - order.indexOf(b.kind));
}

/** An update is new when it happened after the previous visit; nothing is new on a first visit. */
export function isNewSince(update: CaseUpdate, lastSeen: number | null): boolean {
  return lastSeen !== null && update.at > lastSeen;
}
