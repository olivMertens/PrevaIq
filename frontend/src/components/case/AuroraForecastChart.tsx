'use client';

import { useTranslations } from 'next-intl';
import type { AuroraForecast } from '@/lib/api';

type ForecastPoint = AuroraForecast['forecast']['series'][number];

const WIDTH = 640;
const HEIGHT = 210;
const LEFT = 58;
const RIGHT = 14;
const PLOT_WIDTH = WIDTH - LEFT - RIGHT;

function linePath(
  points: ForecastPoint[],
  valueOf: (point: ForecastPoint) => number | null,
  top: number,
  rowHeight: number,
): string {
  const values = points.map(valueOf);
  const numeric = values.filter((value): value is number => value != null);
  if (numeric.length === 0) return '';
  const min = Math.min(...numeric);
  const max = Math.max(...numeric);
  const range = max - min || 1;
  return values.reduce((path, value, index) => {
    if (value == null) return path;
    const x = LEFT + (index / Math.max(points.length - 1, 1)) * PLOT_WIDTH;
    const y = top + rowHeight - ((value - min) / range) * (rowHeight - 8) - 4;
    return `${path}${path ? ' L' : 'M'} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }, '');
}

function extent(
  points: ForecastPoint[],
  valueOf: (point: ForecastPoint) => number | null,
): { min: number; max: number } | null {
  const values = points.map(valueOf).filter((value): value is number => value != null);
  return values.length ? { min: Math.min(...values), max: Math.max(...values) } : null;
}

export default function AuroraForecastChart({
  series,
  locale,
  synthetic = false,
}: {
  series: ForecastPoint[];
  locale: string;
  synthetic?: boolean;
}) {
  const t = useTranslations('caseCockpit.aurora.chart');
  const scenario = useTranslations('caseCockpit.aurora.scenario');
  if (series.length === 0) {
    return <p className="text-xs text-slate-500">{t('empty')}</p>;
  }

  const rows = [
    {
      key: 'gust',
      top: 16,
      color: 'var(--app-chart-teal, #0f766e)',
      value: (point: ForecastPoint) => point.wind_gust_ms,
      unit: t('metersPerSecondShort'),
    },
    {
      key: 'rain',
      top: 76,
      color: 'var(--app-chart-blue, #2563eb)',
      value: (point: ForecastPoint) => point.precipitation_mm,
      unit: t('millimetersShort'),
    },
    {
      key: 'temperature',
      top: 136,
      color: 'var(--app-chart-orange, #c2410c)',
      value: (point: ForecastPoint) => point.temperature_c,
      unit: t('celsiusShort'),
    },
  ] as const;
  const rowHeight = 38;
  const dateFormatter = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' });
  const detailFormatter = new Intl.DateTimeFormat(locale, {
    dateStyle: 'short',
    timeStyle: 'short',
  });
  const numberFormatter = new Intl.NumberFormat(locale, {minimumFractionDigits: 1, maximumFractionDigits: 1});
  const labelIndexes = Array.from(new Set([0, Math.floor((series.length - 1) / 2), series.length - 1]));

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-xs font-semibold">{synthetic ? scenario('chartTitle') : t('title')}</p>
        <p className="text-[10px] opacity-70">{t('hourly')}</p>
      </div>
      <div className="overflow-x-auto rounded-md border border-current/10 bg-white/80 p-2">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={synthetic ? scenario('chartLabel') : t('ariaLabel')}
          className="mx-auto block w-full min-w-[34rem] max-w-3xl"
        >
          {rows.map((row) => {
            const values = extent(series, row.value);
            return (
              <g key={row.key}>
                <text x="0" y={row.top + 17} className="fill-slate-600 text-[10px] font-semibold">
                  {t(row.key)}
                </text>
                <line
                  x1={LEFT}
                  x2={WIDTH - RIGHT}
                  y1={row.top + rowHeight}
                  y2={row.top + rowHeight}
                  stroke="#cbd5e1"
                  strokeWidth="1"
                />
                {row.key === 'rain'
                  ? series.map((point, index) => {
                      const value = row.value(point);
                      if (value == null || !values) return null;
                      const max = values.max || 1;
                      const barWidth = Math.max(2, PLOT_WIDTH / Math.max(series.length, 1) - 2);
                      const barHeight = (value / max) * (rowHeight - 4);
                      const center = LEFT + (index / Math.max(series.length - 1, 1)) * PLOT_WIDTH;
                      const x = Math.min(WIDTH - RIGHT - barWidth, Math.max(LEFT, center - barWidth / 2));
                      return (
                        <rect
                          key={point.valid_at}
                          x={x}
                          y={row.top + rowHeight - barHeight}
                          width={barWidth}
                          height={barHeight}
                          rx="1"
                          fill={row.color}
                          opacity="0.75"
                        >
                          <title>{`${detailFormatter.format(new Date(point.valid_at))}: ${numberFormatter.format(value)} ${row.unit}`}</title>
                        </rect>
                      );
                    })
                  : (
                    <path
                      d={linePath(series, row.value, row.top, rowHeight)}
                      fill="none"
                      stroke={row.color}
                      strokeWidth="2.5"
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  )}
                {row.key !== 'rain' && series.map((point, index) => {
                  const value = row.value(point);
                  if (value == null || !values) return null;
                  const range = values.max - values.min || 1;
                  const x = LEFT + (index / Math.max(series.length - 1, 1)) * PLOT_WIDTH;
                  const y = row.top + rowHeight - ((value - values.min) / range) * (rowHeight - 8) - 4;
                  return (
                    <circle key={point.valid_at} cx={x} cy={y} r="2.5" fill={row.color}>
                      <title>{`${detailFormatter.format(new Date(point.valid_at))}: ${numberFormatter.format(value)} ${row.unit}`}</title>
                    </circle>
                  );
                })}
                {values && (
                  <text x={WIDTH - RIGHT} y={row.top + 10} textAnchor="end" className="fill-slate-500 text-[9px]">
                    {`${numberFormatter.format(values.min)}–${numberFormatter.format(values.max)} ${row.unit}`}
                  </text>
                )}
              </g>
            );
          })}
          {labelIndexes.map((index) => {
            const x = LEFT + (index / Math.max(series.length - 1, 1)) * PLOT_WIDTH;
            return (
              <g key={series[index].valid_at}>
                <line x1={x} x2={x} y1="8" y2="188" stroke="#e2e8f0" strokeDasharray="2 3" />
                <text x={x} y="204" textAnchor={index === 0 ? 'start' : index === series.length - 1 ? 'end' : 'middle'} className="fill-slate-500 text-[9px]">
                  {dateFormatter.format(new Date(series[index].valid_at))}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
