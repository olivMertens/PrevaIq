'use client';

import { useEffect, useMemo, useState } from 'react';
import { Clock3, TriangleAlert } from 'lucide-react';
import clsx from 'clsx';
import { useLocale, useTranslations } from 'next-intl';

type CountdownState = 'active' | 'warning' | 'urgent' | 'expired';

export default function AuroraExpiryCountdown({
  expiresAt,
  compact = false,
}: {
  expiresAt: string | null | undefined;
  compact?: boolean;
}) {
  const t = useTranslations('auroraExpiry');
  const locale = useLocale();
  const expiration = useMemo(() => expiresAt ? Date.parse(expiresAt) : Number.NaN, [expiresAt]);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!Number.isFinite(expiration)) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [expiration]);

  if (!Number.isFinite(expiration)) return null;

  const remaining = Math.max(0, expiration - now);
  const totalHours = remaining / 3_600_000;
  const state: CountdownState = remaining === 0
    ? 'expired'
    : totalHours <= 12
      ? 'urgent'
      : totalHours <= 48
        ? 'warning'
        : 'active';
  const days = Math.floor(remaining / 86_400_000);
  const hours = Math.floor((remaining % 86_400_000) / 3_600_000);
  const minutes = Math.floor((remaining % 3_600_000) / 60_000);
  const seconds = Math.floor((remaining % 60_000) / 1000);
  const exact = new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'long',
  }).format(new Date(expiration));

  return (
    <div
      className={clsx(
        'rounded-xl border',
        compact ? 'p-3' : 'p-4',
        state === 'active' && 'border-teal-200 bg-teal-50 text-teal-950',
        state === 'warning' && 'border-amber-300 bg-amber-50 text-amber-950',
        (state === 'urgent' || state === 'expired') && 'border-rose-300 bg-rose-50 text-rose-950',
      )}
    >
      <div className="flex items-start gap-3">
        {state === 'active'
          ? <Clock3 className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
          : <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-semibold">{t(`states.${state}.title`)}</p>
            <p
              role="timer"
              aria-label={state === 'expired' ? t('expired') : t('remainingAccessible', { days, hours, minutes })}
              className={clsx('font-mono font-bold tabular-nums', compact ? 'text-sm' : 'text-xl')}
            >
              {state === 'expired' ? t('expired') : t('remaining', { days, hours, minutes, seconds })}
            </p>
          </div>
          {!compact && <p className="mt-1 text-sm">{t(`states.${state}.body`)}</p>}
          <p className={clsx('opacity-75', compact ? 'mt-1 text-[11px]' : 'mt-2 text-xs')}>
            {t('expiresAt', { value: exact })}
          </p>
        </div>
      </div>
    </div>
  );
}
