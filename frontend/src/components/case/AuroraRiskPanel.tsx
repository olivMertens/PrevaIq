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
import AuroraClaimMetrics from './AuroraClaimMetrics';

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
  const isDemo = status?.mode === 'demo_simulation';
  const demoLocation = isDemo ? status.demo_location : undefined;
  const hasLocation = typeof latitude === 'number' && Number.isFinite(latitude) &&
    typeof longitude === 'number' && Number.isFinite(longitude);
  const forecastLocation = hasLocation && typeof latitude === 'number' && typeof longitude === 'number'
    ? { latitude, longitude } : demoLocation;
  const canRunForecast = !initializing && status?.enabled === true &&
    status.configured && (hasLocation || Boolean(demoLocation)) && !loading;
  const displayedError = error || (savedError ? t(savedError) : null);

  async function runForecast() {
    if (!canRunForecast) {
      setError(t('unavailable'));
      addToast('error', t('unavailable'));
      return;
    }
    if (!forecastLocation) {
      setError(t('locationRequired'));
      addToast('error', t('locationRequired'));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await createAuroraForecast(applicationId, {
        latitude: forecastLocation.latitude,
        longitude: forecastLocation.longitude,
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
  const actionLabel = loading ? t(isDemo ? 'scenario.running' : 'running')
    : forecast ? t(isDemo ? 'scenario.refresh' : 'refresh')
      : t(isDemo ? 'scenario.run' : 'run');

  return (
    <CockpitCard title={t('title')} headingId="cockpit-aurora" aside={
      <button type="button" onClick={runForecast} disabled={!canRunForecast}
        aria-busy={loading} aria-label={actionLabel} title={actionLabel}
        className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 disabled:opacity-50">
        {loading ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
          : forecast ? <RefreshCw className="h-4 w-4" aria-hidden /> : <CloudSun className="h-4 w-4" aria-hidden />}
        {t(loading ? 'claimMetrics.running' : forecast ? 'claimMetrics.refresh' : 'claimMetrics.generate')}
      </button>
    }>
      <div className="space-y-3 px-4 py-3">
        {!forecast && <p className="text-xs text-slate-500">{t(isDemo ? 'scenario.description' : 'description')}</p>}
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
        {!hasLocation && !demoLocation && <p className="text-xs text-slate-600">{t('locationRequired')}</p>}
        <AuroraExpiryCountdown expiresAt={status?.endpoint_expires_at} compact />
        {status?.enabled && !status.configured && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            {t('notConfigured')}
          </p>
        )}
        {loading && (
          isDemo ? <p role="status" className="text-xs text-slate-600">{t('scenario.running')}</p>
            : <AuroraResolvingState horizonHours={status?.default_horizon_hours ?? 12} />
        )}
        {displayedError && <p role="alert" className="text-xs text-amber-800">{displayedError}</p>}
        {forecast && severity && (
          <div className={clsx('rounded-lg border p-3 text-xs', severityClass)}>
            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="flex items-center gap-1.5 font-semibold">
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
                  {t(`severity.${severity}`)}
                </p>
                <p className="text-[11px] opacity-75">
                  {t(isDemo ? 'scenario.result' : 'result', { model: forecast.model, hours: forecast.horizon_hours })}
                </p>
            </div>
            <div className="mt-3"><AuroraClaimMetrics forecast={forecast.forecast} claimDate={claimDate} /></div>
            {context && <p className="mt-2 text-xs">{t(isDemo ? 'scenario.window' : 'summary.window', {
              start: formatDateTime(context.window.starts_at), end: formatDateTime(context.window.ends_at),
              count: context.point_count,
            })}</p>}
            <p className="mt-1 text-[11px] opacity-75">{t('claimMetrics.boundary')}</p>
            {forecast.decision_support.hazard_window && (
              <p className="mt-2 font-medium">
                {t('hazardWindow', {
                  start: formatDateTime(forecast.decision_support.hazard_window.starts_at),
                  end: formatDateTime(forecast.decision_support.hazard_window.ends_at),
                })}
              </p>
            )}
            <details className="mt-3">
              <summary className="cursor-pointer rounded-md border border-current/20 bg-white/70 px-3 py-2 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600">
                {t('claimMetrics.details')}
              </summary>
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
                synthetic={forecast.provenance?.source === 'demo_simulation'}
              />
            </div>}
            {detail === 'chart' && <div>
              <AuroraForecastChart series={forecast.forecast.series} locale={locale}
                synthetic={forecast.provenance?.source === 'demo_simulation'} />
            </div>}
            {detail === 'trace' && <div className="rounded-md border border-current/10 bg-white/70 p-2">
              <p className="font-semibold">{t('evidence.title')}</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
                <dt className="opacity-70">{t(forecast.provenance?.synthetic ? 'scenario.location' : 'evidence.location')}</dt>
                <dd className="text-right font-medium">{forecast.latitude.toFixed(3)}, {forecast.longitude.toFixed(3)}</dd>
                <dt className="opacity-70">{t('evidence.generated')}</dt>
                <dd className="text-right font-medium">{formatDateTime(forecast.requested_at)}</dd>
                {forecast.provenance?.scenario_started_at && <>
                  <dt className="opacity-70">{t('scenario.startsAt')}</dt>
                  <dd className="text-right font-medium">{formatDateTime(forecast.provenance.scenario_started_at)}</dd>
                </>}
                {forecast.initial_condition_at && (
                  <>
                    <dt className="opacity-70">{t('evidence.initialConditions')}</dt>
                    <dd className="text-right font-medium">{formatDateTime(forecast.initial_condition_at)}</dd>
                  </>
                )}
                <dt className="opacity-70">{t('evidence.source')}</dt>
                <dd className="break-all text-right font-medium">
                  {forecast.provenance?.source === 'demo_simulation'
                    ? t('scenario.source')
                    : forecast.provenance?.initial_condition_blob ?? forecast.provenance?.source ?? t('notAvailable')}
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
            {detail === 'trace' && <p className="mt-1 text-[11px] opacity-80">{t('provenance', {
                provider: forecast.provenance?.source === 'demo_simulation'
                  ? t('scenario.provider') : forecast.provenance?.provider ?? t('notAvailable'),
                time: formatDateTime(forecast.requested_at),
              })}</p>}
            </details>
            <p className="mt-2 text-[11px] opacity-80">
              {t(isDemo ? 'scenario.reviewRequired' : 'reviewRequired')}
            </p>
          </div>
        )}
      </div>
    </CockpitCard>
  );
}
