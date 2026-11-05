'use client';

import clsx from 'clsx';
import { CircleCheck, CircleX, TriangleAlert } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { amountBreakdown, type AmountSegment, type CoverageView } from './coverageView';
import { TONE_STYLE } from './coverageTone';

type Money = (value: number) => string;

export const SECTION_TITLE = 'mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500';

const SEGMENT_COLOR: Record<AmountSegment['kind'], string> = {
  covered: TONE_STYLE.covered.bar,
  review: TONE_STYLE.review.bar,
  excluded: TONE_STYLE.excluded.bar,
  unknown: TONE_STYLE.unknown.bar,
  notRetained: 'bg-slate-400',
};

/** The answer first: coverage status, recommended indemnity, what is and is not covered. */
export function CoverageVerdict({ view, claimed, money }: { view: CoverageView; claimed?: number; money: Money }) {
  const t = useTranslations('caseCockpit.coverTab');
  const style = TONE_STYLE[view.tone];
  const { recommended } = view.amounts;
  const event = view.event?.cause ? view.event : undefined;
  return (
    <section className={clsx('rounded-lg border p-4', style.card)}>
      <div className="flex gap-3">
        <style.Icon className={clsx('mt-1 h-6 w-6 flex-shrink-0', style.icon)} aria-hidden />
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t('verdictLabel')}</p>
            <p className="text-lg font-semibold text-slate-900">{t(`tone.${view.tone}`)}</p>
            {recommended !== undefined && (
              <p className="tabular-nums text-slate-800">
                {claimed !== undefined
                  ? t('headline', { recommended: money(recommended), claimed: money(claimed) })
                  : t('headlineNoClaim', { recommended: money(recommended) })}
              </p>
            )}
          </div>
          {view.summary && <p className="text-slate-700">{view.summary}</p>}
          {(view.coveredHighlight || view.notCoveredHighlights.length > 0) && (
            <ul className="space-y-1 text-slate-800">
              {view.coveredHighlight && (
                <li className="flex gap-2">
                  <CircleCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-600" aria-hidden />
                  {t('coveredHighlight', { text: view.coveredHighlight })}
                </li>
              )}
              {view.notCoveredHighlights.length > 0 && (
                <li className="flex gap-2">
                  <CircleX className="mt-0.5 h-4 w-4 flex-shrink-0 text-rose-600" aria-hidden />
                  {t('notCoveredHighlight', { text: view.notCoveredHighlights.join(' · ') })}
                </li>
              )}
            </ul>
          )}
          {event && (
            <p className="text-xs text-slate-600">
              {t(event.covered === true ? 'eventCovered' : event.covered === false ? 'eventNotCovered' : 'event', { cause: event.cause ?? '' })}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

interface AmountsProps {
  view: CoverageView;
  claimed?: number;
  /** Claimed amount as written in the claim, shown when it is not a plain number. */
  claimedText: string;
  deductibleText?: string;
  money: Money;
}

function AmountRow({ label, value, total = false }: { label: string; value: string; total?: boolean }) {
  return (
    <div className={clsx('flex items-baseline justify-between gap-6', total && 'mt-1 border-t border-slate-200 pt-2')}>
      <dt className={total ? 'font-semibold text-slate-900' : 'text-slate-500'}>{label}</dt>
      <dd className={clsx('text-right tabular-nums text-slate-900', total ? 'text-base font-semibold' : 'font-medium')}>{value}</dd>
    </div>
  );
}

/** From the claimed amount to the recommended indemnity, with the split of the claimed amount. */
export function CoverageAmounts({ view, claimed, claimedText, deductibleText, money }: AmountsProps) {
  const t = useTranslations('caseCockpit.coverTab');
  const segments = amountBreakdown(view, claimed);
  const { eligible, recommended } = view.amounts;
  const deductible = view.amounts.deductible ?? view.rules.deductible?.amount;
  const segmentLabel = (kind: AmountSegment['kind']) => (kind === 'notRetained' ? t('notRetained') : t(`tone.${kind}`));

  return (
    <section>
      <h3 className={SECTION_TITLE}>{t('amounts')}</h3>
      {segments.length > 0 && (
        <div className="mb-3">
          <div
            className="flex h-2.5 overflow-hidden rounded-full bg-slate-100"
            role="img"
            aria-label={`${t('breakdownLabel')}: ${segments.map((segment) => `${segmentLabel(segment.kind)} ${money(segment.amount)}`).join(', ')}`}
          >
            {segments.map((segment) => (
              <div key={segment.kind} className={SEGMENT_COLOR[segment.kind]} style={{ width: `${segment.percent}%` }} />
            ))}
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
            {segments.map((segment) => (
              <li key={segment.kind} className="flex items-center gap-1.5">
                <span className={clsx('h-2 w-2 rounded-full', SEGMENT_COLOR[segment.kind])} aria-hidden />
                {segmentLabel(segment.kind)}
                <span className="font-medium tabular-nums text-slate-800">{money(segment.amount)}</span>
                <span className="tabular-nums">{t('share', { percent: segment.percent })}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <dl className="space-y-1.5">
        <AmountRow label={t('claimed')} value={claimed !== undefined ? money(claimed) : claimedText || '—'} />
        {eligible !== undefined && <AmountRow label={t('eligible')} value={money(eligible)} />}
        {(deductible !== undefined || deductibleText) && (
          <AmountRow label={t('deductible')} value={deductible !== undefined ? `− ${money(deductible)}` : deductibleText ?? ''} />
        )}
        {recommended !== undefined && <AmountRow label={t('recommended')} value={money(recommended)} total />}
      </dl>
      {view.deductibleMismatch && (
        <p className="mt-3 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-amber-900">
          <TriangleAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" aria-hidden />
          {t('deductibleMismatch', { coverage: money(view.deductibleMismatch.coverage), settlement: money(view.deductibleMismatch.settlement) })}
        </p>
      )}
      {view.settlementNote && <p className="mt-2 text-slate-600">{view.settlementNote}</p>}
    </section>
  );
}
