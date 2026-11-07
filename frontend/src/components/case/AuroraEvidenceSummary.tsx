'use client';

import { CloudSun, ShieldAlert } from 'lucide-react';
import clsx from 'clsx';
import { useLocale, useTranslations } from 'next-intl';
import { useAuroraEvidence } from './useAuroraEvidence';

export default function AuroraEvidenceSummary({
  applicationId, onOpen,
}: {applicationId: string; onOpen?: () => void}) {
  const t = useTranslations('caseCockpit.aurora');
  const locale = useLocale();
  const {forecast, context, status, error, initializing} = useAuroraEvidence(applicationId);
  const support = forecast?.decision_support;
  const riskStyle = support && {
    low: 'border-emerald-200 bg-emerald-50 text-emerald-950',
    moderate: 'border-amber-200 bg-amber-50 text-amber-950',
    high: 'border-orange-200 bg-orange-50 text-orange-950',
    critical: 'border-rose-200 bg-rose-50 text-rose-950',
  }[support.severity];
  const format = (value: string) => new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date(value));
  return (
    <section aria-label={t('summary.title')} className="rounded-xl border border-teal-200 bg-teal-50 p-4 text-sm text-teal-950">
      <div className="flex items-start justify-between gap-3">
        <h3 className="flex items-center gap-2 font-semibold"><CloudSun className="h-4 w-4" aria-hidden />{t('summary.title')}</h3>
        {onOpen && <button type="button" onClick={onOpen} className="rounded border border-current/20 px-2 py-1 text-xs">{t('summary.open')}</button>}
      </div>
      {error && <p role="alert" className="mt-2 text-xs">{t(error)}</p>}
      {initializing ? <p role="status" className="mt-2 text-xs">{t('loadingStatus')}</p>
          : !forecast ? !error && <p className="mt-2 text-xs">{t('summary.none')}</p>
            : <div className="mt-2 space-y-2">
              <p className="text-xs font-medium">{t(context ? `summary.${context.kind}` : 'summary.saved')}</p>
              {support && <p className={clsx('flex items-center gap-2 rounded-lg border px-2 py-1 text-xs font-semibold', riskStyle)}>
                <ShieldAlert className="h-4 w-4" aria-hidden />
                {t('summary.risk', {severity: t(`severity.${support.severity}`)})}
              </p>}
              <dl className="grid grid-cols-2 gap-3 text-xs">
                <div><dt>{t('maxGust')}</dt><dd className="font-semibold">{forecast.forecast.max_wind_gust_ms == null ? t('notAvailable') : t('metersPerSecond', {value: forecast.forecast.max_wind_gust_ms})}</dd></div>
                <div><dt>{t('precipitation')}</dt><dd className="font-semibold">{t('millimeters', {value: forecast.forecast.total_precipitation_mm})}</dd></div>
              </dl>
              {context && <p className="text-xs">{t('summary.window', {start: format(context.window.starts_at), end: format(context.window.ends_at), count: context.point_count})}</p>}
              {support && <details className="text-xs">
                <summary className="cursor-pointer font-semibold">{t('summary.review')} · {t('summary.customer')}</summary>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <p>{t('summary.reviewScope')}</p>
                  <p>{t('summary.customerScope')}</p>
                </div>
              </details>}
              <p className="text-xs">{t('summary.boundary')}</p>
            </div>}
      {status?.enabled === false && <p className="mt-2 text-xs font-medium">{t('summary.inferenceUnavailable')}</p>}
    </section>
  );
}
