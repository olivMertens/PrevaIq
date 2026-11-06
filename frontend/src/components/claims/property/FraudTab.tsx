'use client';

import { CircleCheck, CircleX, Eye, Loader2, Play, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { useLocale, useTranslations } from 'next-intl';
import type { FraudAnalysisResponse } from '@/lib/api';
import { SEVERITY_STYLE, SeverityIcon } from '@/components/case/caseUi';
import type { SignalSeverity } from '@/components/case/caseSignals';

interface FraudTabProps {
  result: FraudAnalysisResponse | null;
  running: boolean;
  progress: number;
  onOpenReport: () => void;
  onRun: () => void;
}

const PRIORITY_SEVERITY: Record<string, SignalSeverity> = { high: 'critical', medium: 'warning', low: 'info' };
const BAND_STYLE: Record<string, string> = {
  HIGH: 'border-rose-200 bg-rose-50 text-rose-900',
  MODERATE: 'border-amber-200 bg-amber-50 text-amber-900',
  LOW: 'border-emerald-200 bg-emerald-50 text-emerald-900',
};

/** Fraud verdict, reasons and concordance; the full report (and re-run) stays one click away. */
export default function FraudTab({ result, running, progress, onOpenReport, onRun }: FraudTabProps) {
  const t = useTranslations('caseCockpit.fraudTab');
  const tFraud = useTranslations('fraudAnalysis');
  const locale = useLocale();
  const assessment = result?.overall_assessment;
  const band = assessment?.overall_fraud_risk || 'LOW';
  const concordance = assessment?.dossier_concordance;

  const action = (
    <button
      type="button"
      onClick={result ? onOpenReport : onRun}
      disabled={running}
      className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-3 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-60"
    >
      {running ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : result ? <Eye className="h-4 w-4" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
      {running ? t('running', { progress }) : result ? t('openReport') : t('run')}
    </button>
  );

  if (!result || !assessment) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">{t('none')}</p>
        {action}
      </div>
    );
  }

  return (
    <div className="space-y-5 text-sm">
      <div className={clsx('rounded-lg border p-3', BAND_STYLE[band] ?? BAND_STYLE.LOW)}>
        <p className="font-semibold">
          {tFraud.has(`risk.${band}`) ? tFraud(`risk.${band}`) : band} · {Math.round((assessment.risk_score || 0) * 100)}%
          {result.analysis_timestamp && (
            <span className="ml-2 font-normal opacity-80">
              {t('analysedAt', {
                date: new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(result.analysis_timestamp)),
              })}
            </span>
          )}
        </p>
        {assessment.summary && <p className="mt-1">{assessment.summary}</p>}
        {assessment.siu_referral_recommended && assessment.siu_referral_reason && (
          <p className="mt-2"><span className="font-semibold">{t('siuReason')}</span> {assessment.siu_referral_reason}</p>
        )}
      </div>

      {(assessment.attention_items?.length ?? 0) > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{tFraud('attentionItems')}</h3>
          <ul className="space-y-2">
            {assessment.attention_items?.map((item, index) => {
              const severity = PRIORITY_SEVERITY[item.priority] ?? 'info';
              return (
                <li key={index} className={clsx('flex gap-3 rounded-lg border p-3', SEVERITY_STYLE[severity].surface)}>
                  <SeverityIcon severity={severity} className="mt-0.5" />
                  <div>
                    <p className="font-medium text-slate-900">{String(item.label)}</p>
                    <p className="text-slate-700">{String(item.detail)}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {concordance && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {tFraud('dossierConcordance')} · {Math.round((concordance.score || 0) * 100)}%
          </h3>
          <ul className="space-y-1.5">
            {concordance.field_checks?.map((check, index) => (
              <li key={index} className="flex gap-2">
                {check.match
                  ? <CircleCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-700" aria-label={t('match')} />
                  : <CircleX className="mt-0.5 h-4 w-4 flex-shrink-0 text-rose-700" aria-label={t('mismatch')} />}
                <span>
                  <span className="font-medium capitalize text-slate-900">{check.field}</span>
                  <span className="text-slate-600"> — {tFraud('declared')}: {check.declared} · {tFraud('observed')}: {check.observed}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {action}
        <button type="button" disabled={running} onClick={onRun} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50">
          <RefreshCw className="h-4 w-4" aria-hidden />{t('rerun')}
        </button>
      </div>
    </div>
  );
}
