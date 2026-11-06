'use client';

import { useMemo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import type { ApplicationDecision, FraudAnalysisResponse } from '@/lib/api';
import { applicationCurrency, formatAmount } from '@/lib/currency';
import type { ApplicationMetadata } from '@/lib/types';
import { mergeSignals } from '@/components/case/caseSignals';
import { collectCaseUpdates, type CaseUpdateSource } from '@/components/case/caseUpdates';
import { buildRecommendation } from '@/components/case/recommendation';
import type { AmountKpi, CoverItem, CustomerKpi, FraudKpi } from '@/components/case/VerdictBar';
import type { CaseFact } from '@/components/case/CaseFacts';
import type { EvidencePhoto } from '@/components/case/EvidenceStrip';
import type { SettlementState } from '@/components/case/NextSteps';
import { buildPropertySignals } from './buildPropertySignals';
import { cleanLabel } from './CoverTab';
import { getFieldLabel, getFieldValue, parseAmount } from './propertyClaimHelpers';
import type { usePropertyClaimData } from './usePropertyClaimData';

type ClaimData = ReturnType<typeof usePropertyClaimData>;

const EXPERT_THRESHOLD = 5000;
const DECISIONS: ApplicationDecision[] = ['approve', 'approve_with_conditions', 'defer', 'decline'];
const COVER_ORDER: Record<CoverItem['status'], number> = { critical: 0, warning: 1, ok: 2, neutral: 3 };
const SENTIMENT_LEVELS = new Set(['calm', 'moderate', 'stressed', 'critical']);
const FACT_FIELDS = ['FormuleContrat', 'AdresseAssure', 'TelephoneAssure', 'EmailAssure', 'NumeroSocietaire'];

/** Risk band as translated by the cockpit; an unexpected model value falls back to the score. */
function riskBand(band: string | undefined, score: number): 'LOW' | 'MODERATE' | 'HIGH' {
  const normalized = String(band || '').toUpperCase();
  if (normalized === 'LOW' || normalized === 'MODERATE' || normalized === 'HIGH') return normalized;
  return score >= 0.6 ? 'HIGH' : score >= 0.3 ? 'MODERATE' : 'LOW';
}

/** Municipality from an address ("…, 33000 Bordeaux - cave" → "Bordeaux"), else the text itself. */
function municipality(text: string): string {
  const match = text.match(/\b\d{4,5}\s+([A-Za-zÀ-ÖØ-öø-ÿ'’][A-Za-zÀ-ÖØ-öø-ÿ'’\- ]*?)(?=\s*(?:[,;()—–\d]|\s-\s|$))/);
  return match ? match[1].trim() : text.length > 40 ? `${text.slice(0, 40)}…` : text;
}

interface CockpitInput {
  application: ApplicationMetadata | null;
  data: ClaimData;
  fraud: FraudAnalysisResponse | null;
  fraudStatus: { isLoading: boolean; progress: number };
  analyzing: boolean;
  checkedCount: number;
}

/** View model of the property-claims cockpit: signals, recommendation, tiles, facts, updates. */
export function usePropertyCockpit({ application, data, fraud, fraudStatus, analyzing, checkedCount }: CockpitInput) {
  const t = useTranslations('claims');
  const tc = useTranslations('caseCockpit');
  const tNext = useTranslations('nextAction');
  const locale = useLocale();
  const { ef, llmOutputs, files, aiSummary, amountComparison, galleryItems, steps } = data;

  return useMemo(() => {
    const field = (...keys: string[]) => getFieldValue(ef, keys, '');
    const amountRaw = field('MontantEstime', 'TotalIncurred', 'MontantTotal');
    const amount = parseAmount(amountRaw);
    const currency = applicationCurrency(application);
    const money = (value: number) => formatAmount(value, currency, locale, { maximumFractionDigits: 0 });
    const hasAmount = Number.isFinite(amount) && amount > 0;
    const overclaimPercent = amountComparison?.hasOverclaim ? Math.round(amountComparison.pctDelta) : undefined;

    const raw = buildPropertySignals(
      {
        fraud,
        amount: hasAmount ? amount : 0,
        amountLabel: hasAmount ? money(amount) : amountRaw,
        overclaim: amountComparison?.hasOverclaim
          ? { claimed: money(amountComparison.claimed), recommended: money(amountComparison.recommended), percent: Math.round(amountComparison.pctDelta) }
          : null,
        nature: field('NatureSinistre', 'CauseOfLoss'),
        thirdParty: field('TiersImplique'),
        urgency: field('NiveauUrgence'),
        preexisting: field('PreexistingDamage'),
        description: field('DescriptionSinistre'),
        llmOutputs,
        fileNames: files.map((file) => file.filename),
      },
      t,
      tc,
    );
    const signals = mergeSignals(raw);
    const criticalCount = signals.filter((signal) => signal.severity === 'critical').length;

    const assessment = fraud?.overall_assessment;
    const recommendation = buildRecommendation(
      {
        analysisComplete: !!aiSummary && !analyzing,
        fraudRisk: assessment?.risk_score ?? 0,
        siuRecommended: !!assessment?.siu_referral_recommended,
        inconsistentStatement: fraud?.declaration_verification?.overall_consistent === false,
        amount: hasAmount ? amount : 0,
        amountLabel: money(hasAmount ? amount : 0),
        thresholdLabel: money(EXPERT_THRESHOLD),
      },
      tNext,
    );
    const recorded = (llmOutputs.decision as { decision?: string } | undefined)?.decision;
    const recordedDecision = DECISIONS.includes(recorded as ApplicationDecision) ? (recorded as ApplicationDecision) : null;

    const amountKpi: AmountKpi = {
      label: hasAmount ? money(amount) : amountRaw || null,
      expertRequired: hasAmount && amount > EXPERT_THRESHOLD,
      thresholdLabel: money(EXPERT_THRESHOLD),
      overclaimPercent,
    };
    const fraudKpi: FraudKpi = fraudStatus.isLoading
      ? { state: 'running', progress: fraudStatus.progress }
      : assessment
        ? {
          state: 'done',
          score: Math.round((assessment.risk_score || 0) * 100),
          band: riskBand(assessment.overall_fraud_risk, assessment.risk_score || 0),
          siu: !!assessment.siu_referral_recommended,
        }
        : { state: 'none' };

    const labels = application?.context_labels || [];
    const web = fraud?.web_intelligence as ({ event_verified?: boolean | null; error?: string; skipped?: string } | undefined);
    const cover: CoverItem[] = [
      ...labels
        .filter((label) => label.type === 'verification' || label.type === 'alert')
        .map((label): CoverItem => ({
          label: cleanLabel(label.label),
          status: label.urgency === 'success' ? 'ok' : label.urgency === 'critical' ? 'critical' : 'warning',
        })),
      ...(web && !web.error && !web.skipped && web.event_verified != null
        ? [{ label: tc(web.event_verified ? 'kpi.eventConfirmed' : 'kpi.eventNotConfirmed'), status: (web.event_verified ? 'ok' : 'warning') as CoverItem['status'] }]
        : []),
      ...labels
        .filter((label) => label.type === 'guarantee')
        .sort((a, b) => Number(b.key.startsWith('garantie_')) - Number(a.key.startsWith('garantie_')))
        .map((label): CoverItem => ({ label: cleanLabel(label.label), status: 'neutral' })),
    ].sort((a, b) => COVER_ORDER[a.status] - COVER_ORDER[b.status]);

    const sentiment = application?.sentiment_analysis;
    const customer: CustomerKpi = sentiment && SENTIMENT_LEVELS.has(sentiment.level)
      ? { level: sentiment.level, score: sentiment.score, summary: sentiment.contextSummary }
      : { level: null };

    const place = field('LieuSinistre');
    const lossDate = field('DateSinistre');
    const contract = field('NumeroContrat', 'NumeroPolice');
    const identity = [
      field('NatureSinistre', 'CauseOfLoss'),
      place ? municipality(place) : '',
      lossDate ? tc('verdict.lossDate', { date: lossDate }) : '',
      contract ? tc('verdict.contract', { number: contract }) : '',
    ].filter(Boolean);

    const facts: CaseFact[] = FACT_FIELDS.map((name) => ({ label: getFieldLabel(name, t), value: field(name) }))
      .filter((fact) => fact.value)
      .slice(0, 4);

    const analyses = fraud?.image_analyses ?? [];
    const photos: EvidencePhoto[] = galleryItems.flatMap((item, galleryIndex) => {
      if (item.type !== 'image') return [];
      const analysis = analyses.find((entry) => entry.filename === item.filename && !entry.error);
      return [{
        filename: item.filename,
        url: item.url,
        score: analysis?.authenticity_score,
        authentic: analysis?.is_likely_authentic,
        galleryIndex,
      }];
    });
    const documentCount = files.filter((file) => !/\.(png|jpe?g|gif|webp|bmp|heic|tiff?)$/i.test(file.filename)).length;

    const updates = application
      ? collectCaseUpdates({ ...application, fraud_analysis: fraud ?? application.fraud_analysis } as unknown as CaseUpdateSource)
      : [];

    const settlement: SettlementState = assessment?.siu_referral_recommended
      ? 'blocked'
      : steps.length > 0 && checkedCount >= steps.length
        ? 'ready'
        : 'locked';

    return {
      signals,
      detectedCount: raw.length,
      criticalCount,
      recommendation,
      recordedDecision,
      amountKpi,
      fraudKpi,
      cover,
      customer,
      identity,
      facts,
      photos,
      documentCount,
      updates,
      settlement,
      amount: hasAmount ? amount : 0,
    };
  }, [application, aiSummary, amountComparison, analyzing, checkedCount, ef, files, fraud, fraudStatus, galleryItems, llmOutputs, locale, steps, t, tc, tNext]);
}
