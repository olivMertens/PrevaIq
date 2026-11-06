'use client';

import { CircleCheck, CircleHelp, CircleX, ExternalLink, Search } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import type { WebIntelligenceResult } from '@/lib/api';

interface WebCheckTabProps {
  web: (WebIntelligenceResult & { skipped?: string }) | null | undefined;
  running?: boolean;
  onRun?: () => void;
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url.slice(0, 40);
  }
}

function normalizeFinding(finding: unknown) {
  if (typeof finding === 'string') return { title: '', summary: finding, url: '', supports: undefined as boolean | undefined };
  const value = (finding || {}) as Record<string, unknown>;
  return {
    title: String(value.title || value.type || value.category || ''),
    summary: String(value.summary || value.details || value.description || ''),
    url: String(value.source_url || value.source || ''),
    supports: value.supports_claim as boolean | undefined,
  };
}

/** What Microsoft Web IQ checked: verdict, findings with sources, and the exact searches. */
export default function WebCheckTab({ web, running, onRun }: WebCheckTabProps) {
  const t = useTranslations('caseCockpit.webTab');
  const action = onRun && (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">{t('integratedCheck')}</p>
      <button type="button" disabled={running} onClick={onRun} className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-800 disabled:opacity-50">
        <Search className="h-4 w-4" aria-hidden />{running ? t('running') : t('runWithFraud')}
      </button>
    </div>
  );
  if (!web || web.error) return <div className="space-y-3"><p role={web?.error ? 'alert' : undefined} className="text-sm text-slate-600">{web?.error ? t('error') : t('none')}</p>{action}</div>;

  const verdict = web.skipped ? 'skipped' : web.event_verified === true ? 'confirmed' : web.event_verified === false ? 'notConfirmed' : 'unclear';
  const style = {
    confirmed: { Icon: CircleCheck, box: 'border-emerald-200 bg-emerald-50 text-emerald-900' },
    notConfirmed: { Icon: CircleX, box: 'border-amber-200 bg-amber-50 text-amber-900' },
    unclear: { Icon: CircleHelp, box: 'border-slate-200 bg-slate-50 text-slate-800' },
    skipped: { Icon: CircleHelp, box: 'border-slate-200 bg-slate-50 text-slate-800' },
  }[verdict];
  const confidence = Number(web.confidence);
  const findings = (web.findings || []).map(normalizeFinding).filter((finding) => finding.title || finding.summary);
  const sources = Array.from(new Set(web.source_urls || []));

  return (
    <div className="space-y-5 text-sm">
      {action}
      <div className={clsx('flex gap-3 rounded-lg border p-3', style.box)}>
        <style.Icon className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden />
        <div>
          <p className="font-semibold">
            {t(`verdict.${verdict}`)}
            {Number.isFinite(confidence) && confidence > 0 && verdict !== 'skipped' && (
              <span className="font-normal"> · {t('confidence', { value: Math.round((confidence <= 1 ? confidence * 100 : confidence)) })}</span>
            )}
          </p>
          {web.overall_assessment && <p className="mt-1">{web.overall_assessment}</p>}
        </div>
      </div>

      {findings.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('findings')}</h3>
          <ul className="space-y-2">
            {findings.map((finding, index) => {
              const Icon = finding.supports === true ? CircleCheck : finding.supports === false ? CircleX : CircleHelp;
              const color = finding.supports === true ? 'text-emerald-700' : finding.supports === false ? 'text-rose-700' : 'text-slate-500';
              return (
                <li key={index} className="flex gap-3 rounded-lg border border-slate-200 p-3">
                  <Icon className={clsx('mt-0.5 h-4 w-4 flex-shrink-0', color)} aria-hidden />
                  <div className="min-w-0">
                    {finding.title && <p className="font-medium text-slate-900">{finding.title}</p>}
                    {finding.summary && <p className="text-slate-700">{finding.summary}</p>}
                    {finding.url && (
                      <a href={finding.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-indigo-700 hover:underline">
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                        {hostname(finding.url)}
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {(web.search_queries?.length ?? 0) > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('searches')}</h3>
          <ul className="space-y-1.5 text-slate-700">
            {web.search_queries?.map((query) => (
              <li key={query} className="flex items-center gap-2">
                <Search className="h-4 w-4 flex-shrink-0 text-slate-400" aria-hidden />
                <span>{query}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {sources.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('sources', { count: sources.length })}</h3>
          <ul className="flex flex-wrap gap-1.5">
            {sources.map((url) => (
              <li key={url}>
                <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-slate-200">
                  <ExternalLink className="h-3 w-3" aria-hidden />
                  {hostname(url)}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
