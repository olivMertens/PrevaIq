'use client';

import { useTransition } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import clsx from 'clsx';
import { brand } from '@/lib/brand';
import loginStyles from './auth/login.module.css';

const LOCALES = [
  { code: 'en', label: 'EN', flag: '🇬🇧' },
  { code: 'fr', label: 'FR', flag: '🇫🇷' },
  { code: 'de', label: 'DE', flag: '🇩🇪' },
] as const;

/**
 * Language switcher toggle button (EN / FR / DE).
 * Sets a cookie and reloads to apply the new locale across the app.
 */
export default function LanguageSwitcher({ variant = 'default' }: { variant?: 'default' | 'login' }) {
  const t = useTranslations('auth');
  const isLogin = variant === 'login';
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
    <div
      className={isLogin ? loginStyles.languages : 'flex items-center border border-slate-200 rounded-lg overflow-hidden'}
      role={isLogin ? 'group' : undefined}
      aria-label={isLogin ? t('languageLabel') : undefined}
    >
      {isLogin && <span className={loginStyles.languageIcon} aria-hidden>🌐</span>}
      {LOCALES.map((loc) => (
        <button
          key={loc.code}
          type="button"
          aria-pressed={locale === loc.code}
          onClick={() => switchLocale(loc.code)}
          disabled={isPending}
          className={isLogin ? loginStyles.languageOption : clsx(
            'px-2 py-1 text-xs font-medium transition-colors',
            locale === loc.code
              ? 'text-white'
              : 'text-slate-500 hover:bg-slate-100'
          )}
          style={!isLogin && locale === loc.code ? { backgroundColor: brand.primary } : undefined}
          title={isLogin
            ? t(
                loc.code === 'fr'
                  ? 'languageFrench'
                  : loc.code === 'de'
                    ? 'languageGerman'
                    : 'languageEnglish'
              )
            : loc.code === 'fr'
              ? 'Français'
              : loc.code === 'de'
                ? 'Deutsch'
                : 'English'}
        >
          {!isLogin && <span className="hidden 2xl:inline" aria-hidden>{loc.flag} </span>}{loc.label}
        </button>
      ))}
    </div>
  );
}
