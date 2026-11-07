'use client';

import { useState } from 'react';
import { CloudSun, LoaderCircle, PhoneCall, RefreshCw, ShieldAlert } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import clsx from 'clsx';
import {
  APIError,
  createAuroraForecast,
} from '@/lib/api';
import { CockpitCard } from './caseUi';
import AuroraForecastChart from './AuroraForecastChart';
import AuroraStormTimeline, { AuroraResolvingState } from './AuroraStormTimeline';
import AuroraExpiryCountdown from '@/components/aurora/AuroraExpiryCountdown';
import CaseTabs from './CaseTabs';
import { useAuroraEvidence } from './useAuroraEvidence';
import { useToast } from '@/lib/ToastProvider';

type DetailTab = 'chart' | 'timeline' | 'trace' | 'actions';

export default function AuroraRiskPanel({
  applicationId,
  latitude,
  longitude,
  claimDate,
}: {
  applicationId: string;
  latitude?: number;
  longitude?: number;
  claimDate?: string;
}) {
  const t = useTranslations('caseCockpit.aurora');
  const locale = useLocale();
  const {addToast} = useToast();
  const {status, forecast, context, error: savedError, initializing, setForecast} = useAuroraEvidence(applicationId);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<DetailTab>('chart');
  const hasLocation = typeof latitude === 'number' && Number.isFinite(latitude) &&
    typeof longitude === 'number' && Number.isFinite(longitude);
  const canRunForecast = !initializing && status?.enabled === true &&
    status.configured && hasLocation && !loading;
  const displayedError = error || (savedError ? t(savedError) : null);

  async function runForecast() {
    if (!canRunForecast) {
      setError(t('unavailable'));
      addToast('error', t('unavailable'));
      return;
    }
    if (!hasLocation) {
      setError(t('locationRequired'));
      addToast('error', t('locationRequired'));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await createAuroraForecast(applicationId, {
        latitude,
        longitude,
        horizon_hours: status?.default_horizon_hours ?? 12,
        ensemble: false,
      });
      setForecast(response.result, response.context);
    } catch (cause) {
      const message = cause instanceof APIError && cause.code === 'aurora_not_configured'
        ? t('notConfigured') : t('error');
      setError(message);
      addToast('error', message);
    } finally {
      setLoading(false);
    }
  }

  const severity = forecast?.decision_support?.severity;
  const severityClass = severity
    ? {
        low: 'border-emerald-200 bg-emerald-50 text-emerald-950',
        moderate: 'border-amber-200 bg-amber-50 text-amber-950',
        high: 'border-orange-200 bg-orange-50 text-orange-950',
        critical: 'border-rose-200 bg-rose-50 text-rose-950',
      }[severity]
    : '';
  const formatDateTime = (value: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
      new Date(value),
    );

  return (
    <CockpitCard title={t('title')} headingId="cockpit-aurora">
      <div className="space-y-3 px-4 py-3">
        <p className="text-xs text-slate-500">{t('description')}</p>
        {initializing && <p role="status" className="text-sm text-slate-600">{t('loadingStatus')}</p>}
        {(status?.enabled === false || (!initializing && !status)) && (
          <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
            <p className="font-semibold">{t('unavailable')}</p>
            {status?.enabled === false && (
              <p className="mt-1">
                {t(status.disabled_reason === 'blob_access_denied' ? 'blobAccessDenied' : 'disabled')}
              </p>
            )}
          </div>
        )}
        {!hasLocation && <p className="text-xs text-slate-600">{t('locationRequired')}</p>}
        <AuroraExpiryCountdown expiresAt={status?.endpoint_expires_at} compact />
        {status?.enabled && !status.configured && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            {t('notConfigured')}
          </p>
        )}
        {!forecast?.decision_support && (
          <button
            type="button"
            onClick={runForecast}
            disabled={!canRunForecast}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-60"
          >
            {loading ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <CloudSun className="h-3.5 w-3.5" aria-hidden />}
            {loading ? t('running') : forecast ? t('refresh') : t('run')}
          </button>
        )}
        {loading && (
          <AuroraResolvingState horizonHours={status?.default_horizon_hours ?? 12} />
        )}
        {displayedError && <p role="alert" className="text-xs text-amber-800">{displayedError}</p>}
        {forecast && severity && (
          <div className={clsx('rounded-lg border p-3 text-xs', severityClass)}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="flex items-center gap-1.5 font-semibold">
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
                  {t(`severity.${severity}`)}
                </p>
                <p className="mt-1">
                  {t('result', { model: forecast.model, hours: forecast.horizon_hours })}
                </p>
                <p className="mt-1 font-medium">{t(context ? `summary.${context.kind}` : 'summary.saved')}</p>
              </div>
              <button
                type="button"
                onClick={runForecast}
                disabled={!canRunForecast}
                className="inline-flex items-center gap-1 rounded-md border border-current/20 px-2 py-1 font-medium disabled:opacity-60"
              >
                <RefreshCw className={clsx('h-3 w-3', loading && 'animate-spin')} aria-hidden />
                {t('refresh')}
              </button>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-2">
              <div>
                <dt className="text-[11px] text-teal-700">{t('maxGust')}</dt>
                <dd className="font-semibold">
                  {forecast.forecast.max_wind_gust_ms == null
                    ? t('notAvailable')
                    : t('metersPerSecond', { value: forecast.forecast.max_wind_gust_ms })}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] text-teal-700">{t('precipitation')}</dt>
                <dd className="font-semibold">
                  {t('millimeters', { value: forecast.forecast.total_precipitation_mm })}
                </dd>
              </div>
            </dl>
            {context && <p className="mt-2 text-xs">{t('summary.window', {
              start: formatDateTime(context.window.starts_at), end: formatDateTime(context.window.ends_at),
              count: context.point_count,
            })}</p>}
            <p className="mt-2 text-[11px]">{t('summary.boundary')}</p>
            {forecast.decision_support.hazard_window && (
              <p className="mt-2 font-medium">
                {t('hazardWindow', {
                  start: formatDateTime(forecast.decision_support.hazard_window.starts_at),
                  end: formatDateTime(forecast.decision_support.hazard_window.ends_at),
                })}
              </p>
            )}
            <div className="mt-3"><CaseTabs<DetailTab> idPrefix="aurora-detail" label={t('details.title')}
              tabs={(['chart', 'timeline', 'trace', 'actions'] as const).map(id => ({id, label: t(`details.${id}`)}))}
              active={detail} onChange={setDetail} /></div>
            <div role="tabpanel" id={`aurora-detail-${detail}-panel`}
              aria-labelledby={`aurora-detail-${detail}-tab`} tabIndex={0} className="mt-3">
            {detail === 'timeline' && <div>
              <AuroraStormTimeline
                key={forecast.request_id}
                series={forecast.forecast.series}
                hazardWindow={forecast.decision_support.hazard_window}
                claimDate={claimDate}
                locale={locale}
              />
            </div>}
            {detail === 'chart' && <div>
              <AuroraForecastChart series={forecast.forecast.series} locale={locale} />
            </div>}
            {detail === 'trace' && <div className="rounded-md border border-current/10 bg-white/70 p-2">
              <p className="font-semibold">{t('evidence.title')}</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
                <dt className="opacity-70">{t('evidence.location')}</dt>
                <dd className="text-right font-medium">{forecast.latitude.toFixed(3)}, {forecast.longitude.toFixed(3)}</dd>
                <dt className="opacity-70">{t('evidence.generated')}</dt>
                <dd className="text-right font-medium">{formatDateTime(forecast.requested_at)}</dd>
                {forecast.initial_condition_at && (
                  <>
                    <dt className="opacity-70">{t('evidence.initialConditions')}</dt>
                    <dd className="text-right font-medium">{formatDateTime(forecast.initial_condition_at)}</dd>
                  </>
                )}
                <dt className="opacity-70">{t('evidence.source')}</dt>
                <dd className="break-all text-right font-medium">
                  {forecast.provenance.initial_condition_blob ?? forecast.provenance.source}
                </dd>
              </dl>
            </div>}
            {detail === 'actions' && <><div className="rounded-md bg-white/70 p-2">
              <p className="font-semibold">{t('recommendedActions')}</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {forecast.decision_support.recommended_actions.map((action) => (
                  <li key={action}>{t(`actions.${action}`)}</li>
                ))}
              </ul>
            </div>
            <div className="mt-2 rounded-md bg-white/70 p-2">
              <p className="flex items-center gap-1 font-semibold">
                <PhoneCall className="h-3.5 w-3.5" aria-hidden />
                {t('customerCall')}
              </p>
              <p className="mt-1">{t('summary.customerScope')}</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {forecast.decision_support.customer_talking_points.map((point) => (
                  <li key={point}>{t(`talkingPoints.${point}`)}</li>
                ))}
              </ul>
            </div>
            </>}
            </div>
            <p className="mt-2 text-[11px] opacity-80">
              {t('provenance', {
                provider: forecast.provenance.provider,
                time: formatDateTime(forecast.requested_at),
              })}
            </p>
            <p className="mt-1 text-[11px] font-medium">{t('reviewRequired')}</p>
          </div>
        )}
      </div>
    </CockpitCard>
  );
}
