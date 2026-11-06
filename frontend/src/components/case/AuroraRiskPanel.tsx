'use client';

import { useEffect, useState } from 'react';
import { CloudSun, LoaderCircle, PhoneCall, RefreshCw, ShieldAlert } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import clsx from 'clsx';
import {
  APIError,
  createAuroraForecast,
  getAuroraForecast,
  getAuroraStatus,
  type AuroraForecast,
  type AuroraStatus,
} from '@/lib/api';
import { CockpitCard } from './caseUi';
import AuroraForecastChart from './AuroraForecastChart';

export default function AuroraRiskPanel({
  applicationId,
  latitude,
  longitude,
}: {
  applicationId: string;
  latitude: number;
  longitude: number;
}) {
  const t = useTranslations('caseCockpit.aurora');
  const locale = useLocale();
  const [status, setStatus] = useState<AuroraStatus | null>(null);
  const [forecast, setForecast] = useState<AuroraForecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.allSettled([getAuroraStatus(), getAuroraForecast(applicationId)]).then(
      ([statusResult, forecastResult]) => {
        if (!active) return;
        if (statusResult.status === 'fulfilled') {
          setStatus(statusResult.value);
        } else {
          setError(t('statusError'));
        }
        if (forecastResult.status === 'fulfilled') {
          setForecast(forecastResult.value.result);
        } else if (!(forecastResult.reason instanceof APIError && forecastResult.reason.status === 404)) {
          setError(t('loadError'));
        }
        setInitializing(false);
      },
    );
    return () => {
      active = false;
    };
  }, [applicationId, t]);

  async function runForecast() {
    setLoading(true);
    setError(null);
    try {
      const response = await createAuroraForecast(applicationId, {
        latitude,
        longitude,
        horizon_hours: status?.default_horizon_hours ?? 12,
        ensemble: false,
      });
      setForecast(response.result);
    } catch (cause) {
      setError(cause instanceof APIError ? cause.message : t('error'));
    } finally {
      setLoading(false);
    }
  }

  if (initializing || status?.enabled === false) return null;

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
        {status && !status.configured && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            {t('notConfigured')}
          </p>
        )}
        {!forecast?.decision_support && (
          <button
            type="button"
            onClick={runForecast}
            disabled={loading || !status?.configured}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-60"
          >
            {loading ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <CloudSun className="h-3.5 w-3.5" aria-hidden />}
            {loading ? t('running') : forecast ? t('refresh') : t('run')}
          </button>
        )}
        {error && <p className="text-xs text-amber-800">{error}</p>}
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
              </div>
              <button
                type="button"
                onClick={runForecast}
                disabled={loading}
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
            {forecast.decision_support.hazard_window && (
              <p className="mt-2 font-medium">
                {t('hazardWindow', {
                  start: formatDateTime(forecast.decision_support.hazard_window.starts_at),
                  end: formatDateTime(forecast.decision_support.hazard_window.ends_at),
                })}
              </p>
            )}
            <div className="mt-3">
              <AuroraForecastChart series={forecast.forecast.series} locale={locale} />
            </div>
            <div className="mt-3 rounded-md border border-current/10 bg-white/70 p-2">
              <p className="font-semibold">{t('evidence.title')}</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
                <dt className="opacity-70">{t('evidence.location')}</dt>
                <dd className="text-right font-medium">{forecast.latitude.toFixed(3)}, {forecast.longitude.toFixed(3)}</dd>
                <dt className="opacity-70">{t('evidence.generated')}</dt>
                <dd className="text-right font-medium">{formatDateTime(forecast.requested_at)}</dd>
                <dt className="opacity-70">{t('evidence.source')}</dt>
                <dd className="text-right font-medium">{forecast.provenance.source}</dd>
              </dl>
            </div>
            <div className="mt-3 rounded-md bg-white/70 p-2">
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
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {forecast.decision_support.customer_talking_points.map((point) => (
                  <li key={point}>{t(`talkingPoints.${point}`)}</li>
                ))}
              </ul>
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
