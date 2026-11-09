'use client';

import { CalendarClock, CloudRain, Wind } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import clsx from 'clsx';
import type { AuroraForecast } from '@/lib/api';
import { assessAuroraClaimWindow } from '@/lib/auroraClaimTime';

export default function AuroraClaimMetrics({
  forecast, claimDate,
}: {forecast: AuroraForecast['forecast']; claimDate?: string}) {
  const t = useTranslations('caseCockpit.aurora');
  const locale = useLocale();
  const scope = assessAuroraClaimWindow(forecast.series, claimDate);
  const warning = scope === 'outside_window' || scope === 'invalid_date';
  const gust = forecast.max_wind_gust_ms;
  const number = new Intl.NumberFormat(locale, {maximumFractionDigits: 1});
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <div className="rounded-lg border border-current/10 bg-white/70 px-3 py-2">
        <dt className="flex items-center gap-1.5 text-[11px] opacity-80">
          <Wind className="h-3.5 w-3.5" aria-hidden />{t('scenario.maxGust')}
        </dt>
        <dd className="mt-1 text-base font-semibold">
          {gust == null ? t('notAvailable') : t('claimMetrics.kilometersPerHour', {
            value: number.format(gust * 3.6),
          })}
        </dd>
        <dd className="mt-0.5 text-[11px] opacity-75">
          {gust == null ? t('claimMetrics.gustHelp')
            : `${t('metersPerSecond', {value: number.format(gust)})} · ${t('claimMetrics.gustHelp')}`}
        </dd>
      </div>
      <div className="rounded-lg border border-current/10 bg-white/70 px-3 py-2">
        <dt className="flex items-center gap-1.5 text-[11px] opacity-80">
          <CloudRain className="h-3.5 w-3.5" aria-hidden />{t('scenario.precipitation')}
        </dt>
        <dd className="mt-1 text-base font-semibold">
          {t('millimeters', {value: number.format(forecast.total_precipitation_mm)})}
        </dd>
        <dd className="mt-0.5 text-[11px] opacity-75">{t('claimMetrics.rainHelp')}</dd>
      </div>
      <div className={clsx(
        'col-span-2 rounded-lg border px-3 py-2 sm:col-span-1',
        warning ? 'border-amber-300 bg-amber-50 text-amber-950' : 'border-current/10 bg-white/70',
      )}>
        <dt className="flex items-center gap-1.5 text-[11px] opacity-80">
          <CalendarClock className="h-3.5 w-3.5" aria-hidden />{t('claimMetrics.dateLabel')}
        </dt>
        <dd className="mt-1 text-xs font-semibold">{t(`claimMetrics.scope.${scope}`)}</dd>
        <dd className="mt-1 text-[11px] opacity-75">{t(`claimMetrics.scopeHelp.${scope}`)}</dd>
      </div>
    </dl>
  );
}
