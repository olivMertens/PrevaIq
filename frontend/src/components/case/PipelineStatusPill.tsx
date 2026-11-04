'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ChevronDown, CircleCheck, Cpu, OctagonAlert, TriangleAlert, X } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';
import { pipelineHealth, type PipelineHealthStatus } from './pipelineHealth';

interface PipelineDetail {
  label: string;
  value: string;
  detail?: string;
}

type WorkbenchT = ReturnType<typeof useTranslations>;

/** "Fallback: <readable reason>"; unknown backend codes are shown as they are. */
function describeFallback(t: WorkbenchT, reason: string): string {
  const key = `fallbackReasons.${reason}`;
  return t('pipelineFallback', { reason: t.has(key) ? t(key) : reason });
}

/** Technical facts about how the case was read (engines, model, budget, review). */
function usePipelineDetails(application: ApplicationMetadata): PipelineDetail[] {
  const t = useTranslations('workbench');
  const provenance = application.extraction_provenance;
  if (!provenance) return [];

  const confidence = provenance.summary?.average_confidence;
  const fieldCount = Object.keys(application.extracted_fields || {}).length || provenance.summary?.field_count || 0;
  const confidenceLabel =
    typeof confidence === 'number'
      ? `${Math.round(confidence * 100)}%`
      : fieldCount > 0
        ? t('pipelineConfidenceUnavailable')
        : '—';
  const markitdownMode = provenance.markitdown?.enabled
    ? t('pipelineMarkitdownEnabled', {
      mode: provenance.markitdown.mode || 'local',
      cu: provenance.markitdown.use_content_understanding ? ' + CU' : '',
    })
    : null;
  const cuAnalyzer =
    provenance.summary?.last_analyzer_id || provenance.content_understanding?.default_analyzer_id || '—';
  const contentUnderstanding = [
    cuAnalyzer,
    provenance.content_understanding?.completion_deployment
      ? `CU ${provenance.content_understanding.completion_deployment}`
      : null,
    provenance.content_understanding?.api_version,
  ].filter(Boolean).join(' · ');
  const attempts = provenance.summary?.attempted_engines?.join(', ');
  const fallbackReason = provenance.summary?.fallback_reason;
  const segments = provenance.segments || [];
  const stages = Object.values(application.orchestration?.stages || {});
  const budgetValue = stages.length
    ? t('pipelineBudgetValue', {
      seconds: Math.round(stages.reduce((sum, s) => sum + (s.elapsed_seconds || 0), 0)),
      tokens: stages.reduce((sum, s) => sum + (s.tokens_used || 0), 0),
    })
    : null;

  const details: PipelineDetail[] = [
    {
      label: t('pipelineExtractionEngine'),
      value: provenance.summary?.selected_engine || '—',
      detail: attempts ? t('pipelineAttempts', { engines: attempts }) : t('pipelineExtractionEngineHelp'),
    },
    { label: t('pipelineLlmModel'), value: provenance.openai?.model || provenance.openai?.deployment || '—' },
    { label: t('pipelineContentUnderstanding'), value: contentUnderstanding || '—' },
    ...(markitdownMode ? [{ label: t('pipelineMarkitdown'), value: markitdownMode }] : []),
    {
      label: t('pipelineSegments'),
      value: segments.length ? String(segments.length) : '—',
      detail: segments.map((segment) => `${segment.pages.join(',')}: ${segment.segment_type}`).join(' · ') || undefined,
    },
    ...(fieldCount > 0 ? [{ label: t('pipelineFields'), value: String(fieldCount) }] : []),
    {
      label: t('pipelineConfidence'),
      value: confidenceLabel,
      detail: fallbackReason ? describeFallback(t, fallbackReason) : undefined,
    },
    ...(budgetValue ? [{ label: t('pipelineBudget'), value: budgetValue }] : []),
  ];
  return details.filter((item) => item.value && item.value !== '—');
}

/** Definition list of the pipeline facts, shared by the pill popover and the deep-dive drawer. */
export function PipelineDetails({ application }: { application: ApplicationMetadata }) {
  const details = usePipelineDetails(application);
  return (
    <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-2 text-sm">
      {details.map((item) => (
        <div key={item.label} className="contents">
          <dt className="text-slate-500">{item.label}</dt>
          <dd className="font-medium text-slate-900">
            {item.value}
            {item.detail && <span className="block text-xs font-normal text-slate-500">{item.detail}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const STATUS_STYLE: Record<PipelineHealthStatus, { pill: string; dot: string; Icon: typeof CircleCheck }> = {
  ok: { pill: 'border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100', dot: 'bg-emerald-500', Icon: CircleCheck },
  review: { pill: 'border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100', dot: 'bg-amber-500', Icon: TriangleAlert },
  problem: { pill: 'border-rose-300 bg-rose-50 text-rose-800 hover:bg-rose-100', dot: 'bg-rose-500', Icon: OctagonAlert },
};

/**
 * One pill instead of a strip of chips: quiet when the pipeline is fine, amber when a
 * review is pending, red (and opened once per session) when something went wrong.
 */
export default function PipelineStatusPill({ application }: { application: ApplicationMetadata }) {
  const t = useTranslations('workbench');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverId = useId();
  const headingId = useId();
  const health = pipelineHealth(application);
  const style = STATUS_STYLE[health.status];
  const hasDetails = !!application.extraction_provenance || !!application.orchestration;

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (health.status !== 'problem') return;
    const key = `prevaiq.pipeline.autoOpened.${application.id}`;
    try {
      if (window.sessionStorage.getItem(key)) return;
      window.sessionStorage.setItem(key, '1');
    } catch {
      // Without storage the popover simply opens on each visit.
    }
    // Opens once per session when a problem first shows; sessionStorage is only readable after mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOpen(true);
  }, [health.status, application.id]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
    const onClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) close();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, [open, close]);

  if (!hasDetails) return null;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={popoverId}
        className={clsx('inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition-colors', style.pill)}
      >
        <Cpu className="h-4 w-4" aria-hidden />
        <span>{t('aiPipeline')}</span>
        <span className={clsx('h-1.5 w-1.5 rounded-full', style.dot)} aria-hidden />
        <span className="font-medium">{t(`pipelineState.${health.status}`)}</span>
        <ChevronDown className={clsx('h-4 w-4 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <div
          id={popoverId}
          role="dialog"
          aria-labelledby={headingId}
          className="absolute right-0 top-full z-[56] mt-2 w-[min(440px,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-4 shadow-2xl"
        >
          <div className="mb-2 flex items-center justify-between">
            <h2 id={headingId} className="font-semibold text-slate-900">{t('pipelineHowRead')}</h2>
            <button type="button" onClick={close} aria-label={t('pipelineClose')} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
          {health.status !== 'ok' && (
            <div
              className={clsx(
                'mb-3 flex items-start gap-2 rounded-lg border p-2.5 text-sm',
                health.status === 'problem' ? 'border-rose-200 bg-rose-50 text-rose-900' : 'border-amber-200 bg-amber-50 text-amber-900',
              )}
            >
              <style.Icon className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
              <div>
                <p className="font-semibold">{t(`pipelineState.${health.status}`)}</p>
                {health.fallbackReason && <p>{describeFallback(t, health.fallbackReason)}</p>}
                {health.reasons.length > 0 && (
                  <p>
                    {health.reasons
                      .map((code) => (t.has(`reviewReasons.${code}`) ? t(`reviewReasons.${code}`) : code))
                      .join(' · ')}
                  </p>
                )}
                {health.status === 'review' && <p className="mt-1 text-xs opacity-80">{t('pipelineReviewClears')}</p>}
              </div>
            </div>
          )}
          <PipelineDetails application={application} />
        </div>
      )}
    </div>
  );
}
