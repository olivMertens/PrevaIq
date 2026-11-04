'use client';

import { CircleCheck, CircleX, ExternalLink, TriangleAlert, Umbrella } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ContextLabel } from '@/lib/types';
import MarkdownText from './MarkdownText';

interface CoverTabProps {
  labels: ContextLabel[];
  claimed: string | null;
  recommended: string | null;
  deltaPercent?: number;
  deductible?: string;
  coverageText: string;
}

/** Backend labels carry their own ✓/✗ glyph; the cockpit shows a real icon instead. */
export function cleanLabel(label: string): string {
  return String(label).replace(/^[\s✓✔✗✘×]+/u, '').trim();
}

function LabelRow({ label }: { label: ContextLabel }) {
  const status = label.urgency === 'success' ? 'ok' : label.urgency === 'critical' ? 'critical' : label.type === 'guarantee' ? 'neutral' : 'warning';
  const Icon = { ok: CircleCheck, critical: CircleX, warning: TriangleAlert, neutral: Umbrella }[status];
  const color = { ok: 'text-emerald-700', critical: 'text-rose-700', warning: 'text-amber-700', neutral: 'text-slate-500' }[status];
  let host = '';
  if (label.source_url) {
    try { host = new URL(label.source_url).hostname.replace(/^www\./, ''); } catch { host = ''; }
  }
  return (
    <li className="flex gap-3 rounded-lg border border-slate-200 p-3">
      <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${color}`} aria-hidden />
      <div className="min-w-0">
        <p className="font-medium text-slate-900">{cleanLabel(label.label)}</p>
        {typeof label.tooltip === 'string' && label.tooltip && <p className="text-slate-600">{label.tooltip}</p>}
        {host && (
          <a href={label.source_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-indigo-700 hover:underline">
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            {host}
          </a>
        )}
      </div>
    </li>
  );
}

/** Guarantees concerned, coverage checks, amounts and the AI's coverage reasoning. */
export default function CoverTab({ labels, claimed, recommended, deltaPercent, deductible, coverageText }: CoverTabProps) {
  const t = useTranslations('caseCockpit.coverTab');
  const guarantees = labels.filter((label) => label.type === 'guarantee');
  const checks = labels.filter((label) => label.type === 'verification' || label.type === 'alert');

  return (
    <div className="space-y-5 text-sm">
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('amounts')}</h3>
        <dl className="grid grid-cols-[auto,1fr] gap-x-6 gap-y-1.5">
          <dt className="text-slate-500">{t('claimed')}</dt>
          <dd className="font-medium text-slate-900">{claimed ?? '—'}</dd>
          <dt className="text-slate-500">{t('aiEstimate')}</dt>
          <dd className="font-medium text-slate-900">
            {recommended ?? '—'}
            {deltaPercent !== undefined && <span className="ml-2 text-rose-700">{t('delta', { percent: deltaPercent })}</span>}
          </dd>
          {deductible && (
            <>
              <dt className="text-slate-500">{t('deductible')}</dt>
              <dd className="font-medium text-slate-900">{deductible}</dd>
            </>
          )}
        </dl>
      </section>

      {checks.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('checks')}</h3>
          <ul className="space-y-2">{checks.map((label) => <LabelRow key={label.key} label={label} />)}</ul>
        </section>
      )}

      {guarantees.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('guarantees')}</h3>
          <ul className="space-y-2">{guarantees.map((label) => <LabelRow key={label.key} label={label} />)}</ul>
        </section>
      )}

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('aiCoverage')}</h3>
        {coverageText ? <MarkdownText>{coverageText}</MarkdownText> : <p className="text-slate-500">{t('noCoverage')}</p>}
      </section>
    </div>
  );
}
