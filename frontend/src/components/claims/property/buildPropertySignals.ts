// Raw signals for a property claim, merged and ranked by the cockpit (caseSignals.mergeSignals).
import type { FraudAnalysisResponse } from '@/lib/api';
import { classifyTheme, type RawSignal, type SignalSeverity, type SignalTheme } from '@/components/case/caseSignals';
import type { TranslateFn } from './propertyClaimHelpers';

export interface PropertySignalInput {
  fraud: FraudAnalysisResponse | null;
  amount: number;
  amountLabel: string;
  thresholdLabel: string;
  country?: string;
  overclaim: { claimed: string; recommended: string; percent: number } | null;
  nature: string;
  thirdParty: string;
  urgency: string;
  preexisting: string;
  description: string;
  llmOutputs: Record<string, unknown>;
  fileNames: string[];
}

const PRIORITY_SEVERITY: Record<string, SignalSeverity> = { high: 'critical', medium: 'warning', low: 'info' };

const INDICATOR_THEME: Record<string, SignalTheme> = {
  ai_generated_image: 'photos',
  image_manipulation: 'photos',
  filename_mismatch: 'photos',
  suspicious_damage_pattern: 'photos',
  temporal_inconsistency: 'timeline',
  declaration_mismatch: 'statement',
  amount_anomaly: 'amount',
  policy_exclusion: 'policy',
  customer_history_anomaly: 'customer',
};

const WEATHER_CAUSE = /(tempête|tempete|catastrophe|inondation|orage|grêle|grele|storm|flood|hail|unwetter|sturm|hagel|hochwasser|überschwemmung)/i;
const FIRE_CAUSE = /(incendie|fire|brand)/i;
const YES = /^(oui|yes|ja)\b/i;

/**
 * Deterministic evidence first (precise, comparable), then model findings filed by theme,
 * then business rules: duplicates of the same fact collapse when the cockpit merges them.
 */
export function buildPropertySignals(input: PropertySignalInput, t: TranslateFn, tc: TranslateFn): RawSignal[] {
  const raw: RawSignal[] = [];
  const { fraud } = input;

  const images = fraud?.image_analyses ?? [];
  const suspicious = images
    .filter((image) => !image.error && image.is_likely_authentic === false)
    .sort((a, b) => (a.authenticity_score ?? 0) - (b.authenticity_score ?? 0));
  if (suspicious.length > 0) {
    raw.push({
      theme: 'photos',
      severity: 'critical',
      title: tc('signals.suspiciousPhotos', { count: suspicious.length }),
      detail: suspicious
        .slice(0, 2)
        .map((image) => tc('signals.photoScore', { file: image.filename, score: Math.round((image.authenticity_score ?? 0) * 100) }))
        .join(' · '),
      sources: ['photoAnalysis'],
      tab: 'evidence',
    });
  }
  const unchecked = images.filter((image) => image.error).length;
  if (unchecked > 0) {
    raw.push({ theme: 'photos', severity: 'info', title: tc('signals.photosUnchecked', { count: unchecked }), detail: '', sources: ['photoAnalysis'], tab: 'evidence' });
  }

  const declaration = fraud?.declaration_verification;
  if (declaration && declaration.overall_consistent === false) {
    const score = Math.round((declaration.consistency_score ?? 0) * 100);
    raw.push({
      theme: 'statement',
      severity: score < 50 ? 'critical' : 'warning',
      title: tc('signals.statementMismatch'),
      detail: tc('signals.statementMismatchDetail', { score }),
      sources: ['declarationCheck'],
      tab: 'fraud',
    });
  }

  const web = fraud?.web_intelligence as (NonNullable<FraudAnalysisResponse['web_intelligence']> & { skipped?: string }) | undefined;
  if (web && !web.error) {
    const sources = web.source_urls?.length ?? 0;
    if (web.skipped) {
      raw.push({ theme: 'cover', severity: 'info', title: tc('signals.webSkipped'), detail: web.overall_assessment || '', sources: ['webIq'], tab: 'web' });
    } else if (web.event_verified === false) {
      raw.push({ theme: 'cover', severity: 'warning', title: tc('signals.weatherNotConfirmed'), detail: tc('signals.webSources', { count: sources }), sources: ['webIq'], tab: 'web' });
    } else if (web.event_verified === true) {
      raw.push({ theme: 'cover', severity: 'info', title: tc('signals.weatherConfirmed'), detail: tc('signals.webSources', { count: sources }), sources: ['webIq'], tab: 'web' });
    }
  }

  const attention = fraud?.overall_assessment?.attention_items ?? [];
  for (const item of attention) {
    raw.push({
      theme: classifyTheme(String(item.label)),
      severity: PRIORITY_SEVERITY[item.priority] ?? 'info',
      title: String(item.label),
      detail: String(item.detail || ''),
      sources: ['fraudModel'],
    });
  }
  if (attention.length === 0) {
    for (const indicator of fraud?.overall_assessment?.fraud_indicators ?? []) {
      raw.push({
        theme: INDICATOR_THEME[indicator.indicator_type] ?? 'fraud',
        severity: PRIORITY_SEVERITY[indicator.severity] ?? 'info',
        title: String(indicator.description || indicator.indicator_type).slice(0, 120),
        detail: '',
        sources: ['fraudModel'],
      });
    }
  }

  if (input.amount > 5000) {
    raw.push({ theme: 'amount', severity: 'warning', title: t('signals.highAmount'), detail: t('signals.highAmountDetail', { amount: input.amountLabel, threshold: input.thresholdLabel }), sources: ['rule'], tab: 'cover' });
  }
  if (input.overclaim) {
    raw.push({ theme: 'amount', severity: 'warning', title: tc('signals.overclaim'), detail: tc('signals.overclaimDetail', input.overclaim), sources: ['aiAnalysis'], tab: 'cover' });
  }
  if (WEATHER_CAUSE.test(input.nature) && !web) {
    raw.push({ theme: 'cover', severity: 'info', title: t('signals.weatherEvent'), detail: t(input.country?.toUpperCase() === 'CH' ? 'signals.weatherEventDetailCh' : 'signals.weatherEventDetail'), sources: ['rule'], tab: 'web' });
  }
  if (FIRE_CAUSE.test(input.nature)) {
    raw.push({ theme: 'cover', severity: 'warning', title: t('signals.fire'), detail: t('signals.fireDetail'), sources: ['rule'], tab: 'cover' });
  }
  if (YES.test(input.thirdParty.trim())) {
    raw.push({ theme: 'policy', severity: 'warning', title: t('signals.thirdParty'), detail: t('signals.thirdPartyDetail'), sources: ['rule'], tab: 'cover' });
  }
  const urgency = input.urgency.toLowerCase();
  if (['critique', 'eleve', 'élevé', 'critical', 'high', 'kritisch', 'hoch'].includes(urgency)) {
    raw.push({ theme: 'customer', severity: 'warning', title: t('signals.highUrgency'), detail: t('signals.highUrgencyDetail', { urgency: input.urgency }), sources: ['rule'], tab: 'customer' });
  }
  if (['probable', 'certain'].includes(input.preexisting.toLowerCase())) {
    raw.push({ theme: 'photos', severity: 'critical', title: t('signals.preExistingDamage'), detail: t('signals.preExistingDamageDetail'), sources: ['aiAnalysis'], tab: 'evidence' });
  }
  if (/(incohéren|contradictoi|inconsisten|widersprüch)/i.test(input.description)) {
    raw.push({ theme: 'statement', severity: 'critical', title: t('signals.inconsistency'), detail: t('signals.inconsistencyDetail'), sources: ['aiAnalysis'], tab: 'fraud' });
  }

  for (const [sectionName, subsections] of Object.entries(input.llmOutputs)) {
    if (!subsections || typeof subsections !== 'object') continue;
    for (const value of Object.values(subsections as Record<string, unknown>)) {
      const parsed = (value as { parsed?: Record<string, unknown> } | undefined)?.parsed;
      if (!parsed) continue;
      if (Array.isArray(parsed.fraud_indicators) && parsed.fraud_indicators.length > 0) {
        const first = String(parsed.fraud_indicators[0]);
        raw.push({ theme: classifyTheme(first), severity: 'critical', title: t('signals.fraudIndicators'), detail: first, sources: ['aiAnalysis'] });
      }
      if (typeof parsed.exclusions === 'string' && parsed.exclusions && !/aucune|none|keine/i.test(parsed.exclusions)) {
        raw.push({ theme: 'policy', severity: 'warning', title: t('signals.possibleExclusions'), detail: parsed.exclusions.slice(0, 200), sources: ['aiAnalysis'], tab: 'cover' });
      }
      if (sectionName === 'liability_assessment' && parsed.coverage_status) {
        const status = String(parsed.coverage_status);
        if (/(non|exclu|refus|not covered|denied|nicht)/i.test(status)) {
          raw.push({ theme: 'policy', severity: 'critical', title: t('signals.coverageUnconfirmed'), detail: t('signals.statusDetail', { status }), sources: ['aiAnalysis'], tab: 'cover' });
        }
      }
    }
  }

  const names = input.fileNames.map((name) => name.toLowerCase());
  const has = (pattern: RegExp) => names.some((name) => pattern.test(name));
  const missing: string[] = [];
  if (names.length > 0 && !has(/declaration|déclaration|sinistre|schadenmeldung|claim/)) missing.push(t('signals.missingDeclaration'));
  if (!has(/\.(png|jpe?g|gif|webp|bmp|heic)$/)) missing.push(t('signals.missingPhotos'));
  if (!has(/devis|estimate|facture|invoice|rechnung|offerte|kostenvoranschlag/)) missing.push(t('signals.missingEstimate'));
  if (YES.test(input.thirdParty.trim()) && !has(/constat|amiable|accident/)) missing.push(t('signals.missingAccidentReport'));
  if (missing.length > 0) {
    raw.push({ theme: 'documents', severity: 'warning', title: t('signals.missingDocuments', { count: missing.length }), detail: missing.join(' · '), sources: ['rule'], tab: 'evidence' });
  }

  return raw;
}
