'use client';

import { useEffect, useMemo, useState } from 'react';
import { Check, CloudLightning, MapPin, Play, Radar, TimerReset } from 'lucide-react';
import { useTranslations } from 'next-intl';
import clsx from 'clsx';
import type { AuroraForecast } from '@/lib/api';
import { parseAuroraClaimTime } from '@/lib/auroraClaimTime';

type ForecastPoint = AuroraForecast['forecast']['series'][number];
type HazardWindow = AuroraForecast['decision_support']['hazard_window'];
type Phase = 'before' | 'during' | 'after';

const PHASE_STYLES: Record<Phase, string> = {
  before: 'border-sky-200 bg-sky-50 text-sky-950',
  during: 'border-violet-200 bg-violet-50 text-violet-950',
  after: 'border-teal-200 bg-teal-50 text-teal-950',
};

function phaseFor(timestamp: number, hazardWindow: HazardWindow): Phase {
  if (!hazardWindow) return 'after';
  if (timestamp < Date.parse(hazardWindow.starts_at)) return 'before';
  if (timestamp <= Date.parse(hazardWindow.ends_at)) return 'during';
  return 'after';
}

export function AuroraResolvingState({ horizonHours }: { horizonHours: number }) {
  const t = useTranslations('caseCockpit.aurora.resolving');
  const steps = [
    { key: 'location', icon: MapPin },
    { key: 'conditions', icon: Radar },
    { key: 'forecast', icon: CloudLightning },
    { key: 'alignment', icon: TimerReset },
  ] as const;

  return (
    <div
      role="status"
      aria-live="polite"
      className="relative overflow-hidden rounded-xl border border-sky-200 bg-gradient-to-br from-slate-950 via-sky-950 to-teal-900 p-4 text-white"
    >
      <div
        className="pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 animate-[aurora-scan_2.8s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/15 to-transparent motion-reduce:animate-none"
        aria-hidden
      />
      <div className="relative">
        <div className="flex items-start gap-3">
          <div className="relative grid h-10 w-10 flex-none place-items-center rounded-full border border-white/20 bg-white/10">
            <Radar className="h-5 w-5 animate-[spin_4s_linear_infinite] motion-reduce:animate-none" aria-hidden />
            <span className="absolute inset-1 rounded-full border border-dashed border-teal-200/50" aria-hidden />
          </div>
          <div>
            <p className="text-sm font-semibold">{t('title')}</p>
            <p className="mt-1 text-xs text-sky-100">{t('lead', { hours: horizonHours })}</p>
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {steps.map(({ key, icon: Icon }, index) => (
            <div key={key} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
              <span
                className="grid h-7 w-7 flex-none place-items-center rounded-full bg-white/10"
                style={{ animationDelay: `${index * 220}ms` }}
              >
                <Icon className="h-3.5 w-3.5 animate-pulse motion-reduce:animate-none" aria-hidden />
              </span>
              <span className="text-xs">{t(`steps.${key}`)}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-sky-100">{t('bounded')}</p>
      </div>
    </div>
  );
}

export default function AuroraStormTimeline({
  series,
  hazardWindow,
  claimDate,
  locale,
  synthetic = false,
}: {
  series: ForecastPoint[];
  hazardWindow: HazardWindow;
  claimDate?: string;
  locale: string;
  synthetic?: boolean;
}) {
  const t = useTranslations('caseCockpit.aurora.timeline');
  const scenario = useTranslations('caseCockpit.aurora.scenario');
  const [activeIndex, setActiveIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing || series.length < 2) return;
    const timer = window.setTimeout(() => {
      if (activeIndex >= series.length - 1) {
        setPlaying(false);
      } else {
        setActiveIndex(activeIndex + 1);
      }
    }, 650);
    return () => window.clearTimeout(timer);
  }, [activeIndex, playing, series.length]);

  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }),
    [locale],
  );
  const pointsByPhase = useMemo(
    () =>
      series.reduce<Record<Phase, ForecastPoint[]>>(
        (phases, point) => {
          phases[phaseFor(Date.parse(point.valid_at), hazardWindow)].push(point);
          return phases;
        },
        { before: [], during: [], after: [] },
      ),
    [hazardWindow, series],
  );
  if (series.length === 0) return null;

  const start = Date.parse(series[0].valid_at);
  const end = Date.parse(series[series.length - 1].valid_at);
  const duration = Math.max(end - start, 1);
  const current = series[Math.min(activeIndex, series.length - 1)];
  const currentPhase = phaseFor(Date.parse(current.valid_at), hazardWindow);
  const claimInterval = parseAuroraClaimTime(claimDate);
  const claimInRange =
    claimInterval != null && claimInterval.end >= start && claimInterval.start <= end;
  const claimPosition = claimInRange && claimInterval
    ? ((Math.min(Math.max(claimInterval.marker, start), end) - start) / duration) * 100
    : null;
  const progress = series.length === 1 ? 100 : (activeIndex / (series.length - 1)) * 100;
  const phases = ['before', 'during', 'after'] as const;

  function replay() {
    setActiveIndex(0);
    setPlaying(true);
  }

  return (
    <section className="rounded-lg border border-current/10 bg-white/80 p-3" aria-labelledby="aurora-storm-timeline-title">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p id="aurora-storm-timeline-title" className="font-semibold">{synthetic ? scenario('timelineTitle') : t('title')}</p>
          <p className="mt-0.5 text-[11px] opacity-70">{synthetic ? scenario('timelineLead') : t('lead')}</p>
        </div>
        <button
          type="button"
          onClick={replay}
          disabled={playing || series.length < 2}
          className="inline-flex items-center gap-1 rounded-md border border-current/20 px-2 py-1 text-[11px] font-medium disabled:opacity-50"
        >
          <Play className="h-3 w-3" aria-hidden />
          {playing ? t('playing') : t('replay')}
        </button>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {phases.map((phase) => {
          const points = pointsByPhase[phase];
          return (
            <div
              key={phase}
              className={clsx(
                'rounded-lg border p-2 transition-all duration-300',
                PHASE_STYLES[phase],
                currentPhase === phase && 'ring-2 ring-current/20 shadow-sm',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold">{t(`phases.${phase}.title`)}</p>
                {currentPhase === phase && playing && (
                  <span className="h-2 w-2 animate-pulse rounded-full bg-current motion-reduce:animate-none" aria-hidden />
                )}
              </div>
              <p className="mt-1 text-[10px] opacity-75">
                {points.length
                  ? (synthetic ? scenario('pointCount', { count: points.length }) : t('pointCount', { count: points.length }))
                  : t(`phases.${phase}.empty`)}
              </p>
            </div>
          );
        })}
      </div>

      <div className="relative mt-4 pb-6 pt-2">
        <div className="h-2 overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full rounded-full bg-gradient-to-r from-sky-500 via-violet-500 to-teal-500 transition-[width] duration-500 ease-linear motion-reduce:transition-none"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span
          className="absolute top-0 h-6 w-px bg-slate-900 transition-[left] duration-500 ease-linear motion-reduce:transition-none"
          style={{ left: `${progress}%` }}
          aria-hidden
        />
        {claimPosition != null && (
          <span
            className="absolute top-0 h-6 w-0.5 bg-rose-600"
            style={{ left: `${claimPosition}%` }}
            title={t('claimMarker')}
            aria-hidden
          />
        )}
        <span className="absolute bottom-0 left-0 text-[9px] opacity-60">{dateFormatter.format(new Date(start))}</span>
        <span className="absolute bottom-0 right-0 text-[9px] opacity-60">{dateFormatter.format(new Date(end))}</span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <span className="font-medium">{dateFormatter.format(new Date(current.valid_at))}</span>
        <span>{t(`phases.${currentPhase}.title`)}</span>
        {current.wind_gust_ms != null && <span>{t('gust', { value: current.wind_gust_ms })}</span>}
        {current.precipitation_mm != null && <span>{t('rain', { value: current.precipitation_mm })}</span>}
        {current.temperature_c != null && <span>{t('temperature', { value: current.temperature_c })}</span>}
      </div>

      {claimDate && (
        <p className={clsx('mt-2 flex items-center gap-1.5 text-[11px]', claimInRange ? 'text-emerald-800' : 'text-amber-800')}>
          {claimInRange ? <Check className="h-3.5 w-3.5" aria-hidden /> : <TimerReset className="h-3.5 w-3.5" aria-hidden />}
          {!claimInterval ? t('claimInvalid') : claimInRange
            ? t(claimInterval.precision === 'day' ? 'claimDayOverlap' : 'claimAligned', {date: claimDate})
            : t('claimOutside', {date: claimDate})}
        </p>
      )}
      <p className="mt-2 text-[10px] opacity-65">{synthetic ? scenario('timelineBoundary') : t('advisory')}</p>
    </section>
  );
}
