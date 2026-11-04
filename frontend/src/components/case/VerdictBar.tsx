'use client';

import { Banknote, CircleCheck, CircleHelp, CircleX, Clock, Gauge, HeartPulse, ShieldAlert, Sparkles, TriangleAlert, Umbrella, XCircle } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import type { ApplicationDecision } from '@/lib/api';
import type { DeepDiveTab } from './caseSignals';
import type { Recommendation } from './recommendation';

export interface AmountKpi {
  label: string | null;
  expertRequired: boolean;
  thresholdLabel: string;
  overclaimPercent?: number;
}

export interface FraudKpi {
  state: 'none' | 'running' | 'done';
  progress?: number;
  score?: number;
  band?: string;
  siu?: boolean;
}

export interface CoverItem {
  label: string;
  status: 'neutral' | 'ok' | 'warning' | 'critical';
}

export interface CustomerKpi {
  level: 'calm' | 'moderate' | 'stressed' | 'critical' | null;
  score?: number;
  summary?: string;
}

interface VerdictBarProps {
  identity: string[];
  recommendation: Recommendation | null;
  criticalCount: number;
  recordedDecision?: ApplicationDecision | null;
  analysisRunning: boolean;
  amount: AmountKpi;
  fraud: FraudKpi;
  cover: CoverItem[];
  customer: CustomerKpi;
  onValidate: () => void;
  onOtherDecision: () => void;
  onWhy: () => void;
  onRunAnalysis: () => void;
  onOpenTab: (tab: DeepDiveTab) => void;
}

const TONE = {
  critical: { frame: 'border-rose-600 bg-rose-50/70', label: 'text-rose-700', button: 'bg-rose-600 hover:bg-rose-700', Icon: ShieldAlert },
  warning: { frame: 'border-amber-500 bg-amber-50/70', label: 'text-amber-800', button: 'bg-amber-600 hover:bg-amber-700', Icon: TriangleAlert },
  success: { frame: 'border-emerald-600 bg-emerald-50/70', label: 'text-emerald-800', button: 'bg-emerald-600 hover:bg-emerald-700', Icon: CircleCheck },
} as const;

const DECISION_ICON: Record<ApplicationDecision, typeof CircleCheck> = {
  approve: CircleCheck,
  approve_with_conditions: TriangleAlert,
  defer: Clock,
  decline: XCircle,
};

const COVER_ICON = {
  neutral: { Icon: Umbrella, className: 'text-slate-500' },
  ok: { Icon: CircleCheck, className: 'text-emerald-700' },
  warning: { Icon: CircleHelp, className: 'text-amber-700' },
  critical: { Icon: CircleX, className: 'text-rose-700' },
} as const;

const FRAUD_COLOR: Record<string, string> = { HIGH: 'text-rose-700', MODERATE: 'text-amber-700', LOW: 'text-emerald-700' };
const FRAUD_BAR: Record<string, string> = { HIGH: 'bg-rose-600', MODERATE: 'bg-amber-500', LOW: 'bg-emerald-600' };
const CUSTOMER_COLOR = { critical: 'text-rose-700', stressed: 'text-amber-800', moderate: 'text-slate-800', calm: 'text-emerald-800' } as const;

function Tile({ label, Icon, onClick, children }: { label: string; Icon: typeof Gauge; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-w-0 flex-col items-start rounded-lg border border-slate-200 p-3 text-left transition-colors hover:border-indigo-300 hover:bg-indigo-50/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
    >
      <span className="inline-flex items-center gap-1 text-xs text-slate-500">
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {label}
      </span>
      {children}
    </button>
  );
}

/** One recommendation and four facts: what a case handler needs in five seconds. */
export default function VerdictBar({
  identity,
  recommendation,
  criticalCount,
  recordedDecision,
  analysisRunning,
  amount,
  fraud,
  cover,
  customer,
  onValidate,
  onOtherDecision,
  onWhy,
  onRunAnalysis,
  onOpenTab,
}: VerdictBarProps) {
  const t = useTranslations('caseCockpit');
  const tDecisions = useTranslations('decisions');
  const tone = recommendation ? TONE[recommendation.tone] : null;

  const recommendationBlock = recordedDecision ? (
    <div className="flex h-full flex-col justify-between rounded-lg border-l-4 border-indigo-600 bg-indigo-50/60 p-3">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">{t('verdict.decisionLabel')}</p>
        <p className="mt-1 inline-flex items-center gap-2 text-lg font-semibold text-slate-900">
          {(() => { const Icon = DECISION_ICON[recordedDecision]; return <Icon className="h-5 w-5" aria-hidden />; })()}
          {tDecisions(recordedDecision)}
        </p>
      </div>
      <button type="button" onClick={onOtherDecision} className="mt-3 self-start rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
        {t('verdict.change')}
      </button>
    </div>
  ) : recommendation && tone ? (
    <div className={clsx('flex h-full flex-col justify-between rounded-lg border-l-4 p-3', tone.frame)}>
      <div>
        <p className={clsx('inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide', tone.label)}>
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
          {t('verdict.recommendation')}
        </p>
        <p className="mt-1 text-lg font-semibold text-slate-900">{recommendation.title}</p>
        <p className="mt-1 text-sm text-slate-700">
          {criticalCount > 0 ? t('verdict.criticalReason', { count: criticalCount }) : recommendation.reason}{' '}
          <button type="button" onClick={onWhy} className="font-medium text-indigo-700 underline">{t('verdict.why')}</button>
        </p>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={onValidate} className={clsx('inline-flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 font-medium text-white', tone.button)}>
          <tone.Icon className="h-4 w-4" aria-hidden />
          {t('verdict.validate')}
        </button>
        <button type="button" onClick={onOtherDecision} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
          {t('verdict.otherDecision')}
        </button>
      </div>
    </div>
  ) : (
    <div className="flex h-full flex-col justify-between rounded-lg border border-dashed border-slate-300 p-3">
      <p className="text-sm text-slate-600">{analysisRunning ? t('verdict.analysisRunning') : t('verdict.pending')}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {!analysisRunning && (
          <button type="button" onClick={onRunAnalysis} className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700">
            {t('verdict.runAnalysis')}
          </button>
        )}
        <button type="button" onClick={onOtherDecision} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
          {t('verdict.otherDecision')}
        </button>
      </div>
    </div>
  );

  return (
    <section aria-label={t('verdict.label')} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {identity.length > 0 && <p className="mb-3 truncate text-sm text-slate-600" title={identity.join(' · ')}>{identity.join(' · ')}</p>}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 xl:col-span-4">{recommendationBlock}</div>
        <div className="col-span-12 grid grid-cols-2 gap-3 lg:grid-cols-4 xl:col-span-8">
          <Tile label={t('kpi.claimed')} Icon={Banknote} onClick={() => onOpenTab('cover')}>
            <span className="mt-1 text-2xl font-semibold text-slate-900">{amount.label ?? '—'}</span>
            {amount.expertRequired && (
              <span className="mt-1 inline-flex items-center gap-1 text-sm text-amber-800">
                <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
                {t('kpi.expertNeeded', { threshold: amount.thresholdLabel })}
              </span>
            )}
            {amount.overclaimPercent !== undefined && (
              <span className="mt-0.5 text-sm text-rose-700">{t('kpi.overclaim', { percent: amount.overclaimPercent })}</span>
            )}
          </Tile>
          <Tile label={t('kpi.fraudRisk')} Icon={Gauge} onClick={() => onOpenTab('fraud')}>
            {fraud.state === 'done' && fraud.band ? (
              <>
                <span className={clsx('mt-1 text-2xl font-semibold', FRAUD_COLOR[fraud.band] ?? 'text-slate-900')}>
                  {fraud.score}% <span className="text-base">{t(`updates.bands.${fraud.band}`)}</span>
                </span>
                <span className="mt-2 block h-1.5 w-full rounded-full bg-slate-100" role="img" aria-label={t('kpi.fraudBar', { score: fraud.score ?? 0 })}>
                  <span className={clsx('block h-1.5 rounded-full', FRAUD_BAR[fraud.band] ?? 'bg-slate-500')} style={{ width: `${fraud.score ?? 0}%` }} />
                </span>
                {fraud.siu && <span className="mt-1 text-sm text-rose-700">{t('kpi.siuRecommended')}</span>}
              </>
            ) : fraud.state === 'running' ? (
              <>
                <span className="mt-1 text-base font-medium text-purple-700">{t('kpi.analyzing', { progress: fraud.progress ?? 0 })}</span>
                <span className="mt-2 block h-1.5 w-full rounded-full bg-purple-100">
                  <span className="block h-1.5 rounded-full bg-purple-600 transition-all" style={{ width: `${fraud.progress ?? 0}%` }} />
                </span>
              </>
            ) : (
              <span className="mt-1 text-sm text-slate-600">{t('kpi.fraudNotRun')}</span>
            )}
          </Tile>
          <Tile label={t('kpi.cover')} Icon={Umbrella} onClick={() => onOpenTab('web')}>
            {cover.length === 0 ? (
              <span className="mt-1 text-sm text-slate-600">{t('kpi.coverUnknown')}</span>
            ) : (
              <ul className="mt-1 space-y-0.5 text-sm">
                {cover.slice(0, 3).map((item) => {
                  const { Icon, className } = COVER_ICON[item.status];
                  return (
                    <li key={item.label} className={clsx('flex items-center gap-1.5', className)}>
                      <Icon className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />
                      <span className="truncate">{item.label}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Tile>
          <Tile label={t('kpi.customer')} Icon={HeartPulse} onClick={() => onOpenTab('customer')}>
            {customer.level ? (
              <>
                <span className={clsx('mt-1 text-base font-semibold', CUSTOMER_COLOR[customer.level])}>
                  {t(`kpi.customerLevels.${customer.level}`)}
                  {customer.score !== undefined && <span className="ml-1 text-sm font-normal text-slate-500">{t('kpi.score', { score: customer.score })}</span>}
                </span>
                {customer.summary && <span className="mt-1 line-clamp-2 text-sm text-slate-600">{customer.summary}</span>}
              </>
            ) : (
              <span className="mt-1 text-sm text-slate-600">{t('kpi.customerUnknown')}</span>
            )}
          </Tile>
        </div>
      </div>
    </section>
  );
}
