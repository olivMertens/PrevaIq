'use client';

import { useMemo, useState } from 'react';
import { ArrowRight, ChevronDown, ChevronUp, CircleCheck, ExternalLink } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import {
  THEME_FILTER,
  countByFilter,
  splitEssential,
  type CaseSignal,
  type SignalFilter,
} from './caseSignals';
import { CockpitCard, SEVERITY_STYLE, SeverityIcon, SourceChip } from './caseUi';

export type Density = 'essential' | 'detailed';

interface AttentionListProps {
  signals: CaseSignal[];
  detectedCount: number;
  analysisReady: boolean;
  density: Density;
  onDensityChange: (density: Density) => void;
  onOpenEvidence: (signal: CaseSignal) => void;
}

const FILTERS: SignalFilter[] = ['all', 'fraud', 'cover', 'amount', 'documents', 'customer'];

function SignalItem({
  signal,
  detailed,
  onOpenEvidence,
}: {
  signal: CaseSignal;
  detailed: boolean;
  onOpenEvidence: (signal: CaseSignal) => void;
}) {
  const t = useTranslations('caseCockpit');
  const style = SEVERITY_STYLE[signal.severity];
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <SeverityIcon severity={signal.severity} className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <p className={clsx('text-xs font-semibold uppercase tracking-wide', style.text)}>
          {t(`severity.${signal.severity}`)} · {t(`themes.${signal.theme}`)}
        </p>
        <p className="font-semibold text-slate-900">{signal.title}</p>
        {signal.detail && (
          <p className={clsx('text-sm text-slate-600', !detailed && 'line-clamp-2')}>{signal.detail}</p>
        )}
        {detailed && signal.merged.length > 0 && (
          <p className="mt-1 text-xs text-slate-500">{t('attention.alsoFlagged', { titles: signal.merged.join(' · ') })}</p>
        )}
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {signal.sources.map((source) => <SourceChip key={source} source={source} />)}
          {signal.sourceUrl && (
            <a
              href={signal.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-indigo-700 hover:underline"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              {t('attention.source')}
            </a>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onOpenEvidence(signal)}
        className="inline-flex flex-shrink-0 items-center gap-1 rounded-md px-2 py-1 text-sm font-medium text-indigo-700 hover:bg-indigo-50"
        aria-label={t('attention.evidenceFor', { title: signal.title })}
      >
        {t('attention.evidence')}
        <ArrowRight className="h-4 w-4" aria-hidden />
      </button>
    </li>
  );
}

/** Deduplicated, ranked signals: a few lines to read, the evidence one click away. */
export default function AttentionList({
  signals,
  detectedCount,
  analysisReady,
  density,
  onDensityChange,
  onOpenEvidence,
}: AttentionListProps) {
  const t = useTranslations('caseCockpit');
  const [filter, setFilter] = useState<SignalFilter>('all');
  const [showAll, setShowAll] = useState(false);
  const counts = useMemo(() => countByFilter(signals), [signals]);
  const filtered = useMemo(
    () => (filter === 'all' ? signals : signals.filter((signal) => THEME_FILTER[signal.theme] === filter)),
    [signals, filter],
  );
  const detailed = density === 'detailed';
  const { shown, hidden } = useMemo(
    () => (detailed ? { shown: filtered, hidden: [] } : splitEssential(filtered, 5)),
    [filtered, detailed],
  );
  const visible = showAll ? [...shown, ...hidden] : shown;

  const aside = (
    <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
      <div role="group" aria-label={t('attention.filtersLabel')} className="flex overflow-hidden rounded-lg border border-slate-200">
        {FILTERS.filter((key) => key === 'all' || counts[key] > 0).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={filter === key}
            onClick={() => { setFilter(key); setShowAll(false); }}
            className={clsx('px-2.5 py-1', filter === key ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-50')}
          >
            {t(`attention.filters.${key}`)} {counts[key]}
          </button>
        ))}
      </div>
      <div role="group" aria-label={t('attention.density.label')} className="flex overflow-hidden rounded-lg border border-slate-200">
        {(['essential', 'detailed'] as const).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={density === key}
            onClick={() => onDensityChange(key)}
            className={clsx('px-2.5 py-1', density === key ? 'bg-indigo-50 font-medium text-indigo-700' : 'text-slate-700 hover:bg-slate-50')}
          >
            {t(`attention.density.${key}`)}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <CockpitCard title={t('attention.title')} headingId="cockpit-attention" aside={signals.length > 0 ? aside : undefined}>
      {!analysisReady ? (
        <p className="px-4 py-6 text-sm text-slate-500">{t('attention.notAnalyzed')}</p>
      ) : signals.length === 0 ? (
        <p className="flex items-center gap-2 px-4 py-6 text-sm text-emerald-800">
          <CircleCheck className="h-5 w-5" aria-hidden />
          {t('attention.empty')}
        </p>
      ) : (
        <>
          <p className="px-4 pt-2 text-xs text-slate-500">
            {t('attention.summary', { shown: visible.length, total: detectedCount })}
          </p>
          <ul className="divide-y divide-slate-100">
            {visible.map((signal) => (
              <SignalItem key={signal.id} signal={signal} detailed={detailed} onOpenEvidence={onOpenEvidence} />
            ))}
          </ul>
          {hidden.length > 0 && (
            <button
              type="button"
              aria-expanded={showAll}
              onClick={() => setShowAll((value) => !value)}
              className="inline-flex w-full items-center justify-center gap-1 border-t border-slate-100 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {showAll ? t('attention.showLess') : t('attention.showMore', { count: hidden.length })}
              {showAll ? <ChevronUp className="h-4 w-4" aria-hidden /> : <ChevronDown className="h-4 w-4" aria-hidden />}
            </button>
          )}
        </>
      )}
    </CockpitCard>
  );
}
