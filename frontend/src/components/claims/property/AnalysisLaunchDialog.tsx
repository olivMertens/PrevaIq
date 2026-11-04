'use client';

import { useEffect, useId, useRef } from 'react';
import { Activity, Loader2, Scale, TriangleAlert, X } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface AnalysisLaunchDialogProps {
  open: boolean;
  loading: boolean;
  error: string | null;
  canLaunch: boolean;
  onClose: () => void;
  onLaunch: () => void;
}

/** Confirms what the AI analysis will do before (re)launching it. */
export default function AnalysisLaunchDialog({ open, loading, error, canLaunch, onClose, onLaunch }: AnalysisLaunchDialogProps) {
  const t = useTranslations('claims');
  const titleId = useId();
  const launchRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    launchRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[80vh] w-full max-w-xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-slate-100 bg-slate-50 px-6 py-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600">
            <Scale className="h-5 w-5" aria-hidden />
          </span>
          <div className="flex-1">
            <h2 id={titleId} className="text-base font-semibold text-slate-900">{t('analysis.liability')}</h2>
            <p className="text-sm text-slate-600">{t('analysis.liabilityDescription')}</p>
          </div>
          <button type="button" onClick={onClose} aria-label={t('documents.close')} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-200">
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-auto p-6 text-sm">
          <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 text-indigo-900">
            <p className="mb-2 font-semibold">{t('analysis.launchDescription')}</p>
            <ul className="list-inside list-disc space-y-1.5">
              <li>{t('analysisDialog.bullet1')}</li>
              <li>{t('analysisDialog.bullet2')}</li>
              <li>{t('analysisDialog.bullet3')}</li>
              <li>{t('analysisDialog.bullet4')}</li>
              <li>{t('analysisDialog.bullet5')}</li>
            </ul>
            <p className="mt-3 font-medium">⏱ {t('analysisDialog.duration')}</p>
          </div>
          {error && (
            <p role="alert" className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-rose-700">
              <TriangleAlert className="h-4 w-4 flex-shrink-0" aria-hidden />
              {error}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-3 border-t border-slate-100 bg-slate-50 px-6 py-4">
          <button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
            {t('analysis.cancel')}
          </button>
          <button
            ref={launchRef}
            type="button"
            onClick={onLaunch}
            disabled={loading || !canLaunch}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Activity className="h-4 w-4" aria-hidden />}
            {loading ? t('analysis.progressMessage') : t('analysis.launch')}
          </button>
        </div>
      </div>
    </div>
  );
}
