'use client';

import { useTransition } from 'react';
import { useLocale } from 'next-intl';
import clsx from 'clsx';
import { brand } from '@/lib/brand';

const LOCALES = [
  { code: 'en', label: 'EN', flag: '🇬🇧' },
  { code: 'fr', label: 'FR', flag: '🇫🇷' },
] as const;

/**
 * Language switcher toggle button (EN / FR).
 * Sets a cookie and reloads to apply the new locale across the app.
 */
export default function LanguageSwitcher() {
  const locale = useLocale();
  const [isPending, startTransition] = useTransition();

  function switchLocale(newLocale: string) {
    if (newLocale === locale) return;
    startTransition(() => {
      document.cookie = `locale=${newLocale};path=/;max-age=${365 * 24 * 60 * 60};samesite=lax`;
      window.location.reload();
    });
  }

  return (
    <div className="flex items-center border border-slate-200 rounded-lg overflow-hidden">
      {LOCALES.map((loc) => (
        <button
          key={loc.code}
          onClick={() => switchLocale(loc.code)}
          disabled={isPending}
          className={clsx(
            'px-2 py-1 text-xs font-medium transition-colors',
            locale === loc.code
              ? 'text-white'
              : 'text-slate-500 hover:bg-slate-100'
          )}
          style={locale === loc.code ? { backgroundColor: brand.primary } : undefined}
          title={loc.code === 'fr' ? 'Français' : 'English'}
        >
          {loc.flag} {loc.label}
        </button>
      ))}
    </div>
  );
}
