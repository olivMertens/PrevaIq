'use client';

import { useEffect, useId, useRef, useState, useTransition } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Check, ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import { brand } from '@/lib/brand';
import loginStyles from './auth/login.module.css';

export const LOCALES = [
  { code: 'en', label: 'EN', flag: '🇬🇧', translationKey: 'languageEnglish' },
  { code: 'fr', label: 'FR', flag: '🇫🇷', translationKey: 'languageFrench' },
  { code: 'de', label: 'DE', flag: '🇩🇪', translationKey: 'languageGerman' },
  { code: 'de-CH', label: 'DE-CH', flag: '🇨🇭', translationKey: 'languageGermanSwiss' },
] as const;

/** Current locale and a switch that stores the cookie and reloads to apply it everywhere. */
export function useLocaleSwitch() {
  const locale = useLocale();
  const [isPending, startTransition] = useTransition();

  function switchLocale(newLocale: string) {
    if (newLocale === locale) return;
    startTransition(() => {
      document.cookie = `locale=${newLocale};path=/;max-age=${365 * 24 * 60 * 60};samesite=lax`;
      window.location.reload();
    });
  }

  return { locale, isPending, switchLocale };
}

export function LanguageOptions({
  variant = 'default',
  menu = false,
  onSelected,
}: { variant?: 'default' | 'login'; menu?: boolean; onSelected?: () => void }) {
  const t = useTranslations('auth');
  const isLogin = variant === 'login';
  const { locale, isPending, switchLocale } = useLocaleSwitch();
  const [germanOpen, setGermanOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const submenuRef = useRef<HTMLDivElement>(null);
  const submenuId = useId();
  const germanSelected = locale === 'de' || locale === 'de-CH';
  const itemClass = 'flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 focus:bg-slate-100 focus:outline-none disabled:opacity-50';

  useEffect(() => {
    if (!germanOpen) return;
    (submenuRef.current?.querySelector<HTMLElement>('[aria-checked="true"]')
      ?? submenuRef.current?.querySelector<HTMLElement>('button:not(:disabled)'))?.focus();
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setGermanOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [germanOpen]);

  function select(code: string) {
    setGermanOpen(false);
    if (code === locale) triggerRef.current?.focus();
    onSelected?.();
    switchLocale(code);
  }

  function onSubmenuKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Tab') {
      setGermanOpen(false);
      return;
    }
    const items = Array.from(submenuRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === 'Escape' || event.key === 'ArrowLeft') {
      event.preventDefault();
      event.stopPropagation();
      setGermanOpen(false);
      triggerRef.current?.focus();
    } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      event.stopPropagation();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
        : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[next]?.focus();
    }
  }

  return (
    <div
      ref={containerRef}
      className={menu ? '' : isLogin ? loginStyles.languages : 'relative flex items-center border border-slate-200 rounded-lg'}
      role="group"
      aria-label={t('languageLabel')}
    >
      {isLogin && <span className={loginStyles.languageIcon} aria-hidden>🌐</span>}
      {LOCALES.filter(loc => loc.code === 'en' || loc.code === 'fr').map((loc) => (
        <button
          key={loc.code}
          type="button"
          role={menu ? 'menuitemradio' : undefined}
          aria-checked={menu ? locale === loc.code : undefined}
          aria-pressed={menu ? undefined : locale === loc.code}
          onClick={() => select(loc.code)}
          disabled={isPending}
          className={menu ? itemClass : isLogin ? loginStyles.languageOption : clsx(
            'px-2 py-1 text-xs font-medium transition-colors',
            locale === loc.code
              ? 'text-white'
              : 'text-slate-500 hover:bg-slate-100'
          )}
          style={!menu && !isLogin && locale === loc.code ? { backgroundColor: brand.primary } : undefined}
          title={t(loc.translationKey)}
        >
          {menu ? (
            <>
              <span className="w-12 flex-shrink-0 text-xs font-semibold text-slate-500">{loc.label}</span>
              <span className="flex-1">{t(loc.translationKey)}</span>
              {locale === loc.code && <Check className="h-4 w-4 text-indigo-600" aria-hidden />}
            </>
          ) : (
            <>{!isLogin && <span className="hidden 2xl:inline" aria-hidden>{loc.flag} </span>}{loc.label}</>
          )}
        </button>
      ))}
      <div>
        <button
          ref={triggerRef}
          type="button"
          role={menu ? 'menuitem' : undefined}
          aria-haspopup="menu"
          aria-expanded={germanOpen}
          aria-controls={germanOpen ? submenuId : undefined}
          aria-pressed={menu ? undefined : germanSelected}
          title={t(locale === 'de-CH' ? 'languageGermanSwiss' : 'languageGerman')}
          disabled={isPending}
          onClick={() => setGermanOpen(value => !value)}
          onKeyDown={event => {
            if (event.key === 'ArrowRight' || (!menu && event.key === 'ArrowDown')) {
              event.preventDefault();
              event.stopPropagation();
              setGermanOpen(true);
            }
          }}
          className={menu ? itemClass : isLogin ? loginStyles.languageOption : clsx(
            'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium',
            germanSelected ? 'text-white' : 'text-slate-500 hover:bg-slate-100'
          )}
          style={!menu && !isLogin && germanSelected ? { backgroundColor: brand.primary } : undefined}
        >
          {menu ? (
            <>
              <span className="w-12 flex-shrink-0 text-xs font-semibold text-slate-500">DE</span>
              <span className="flex-1">{t('languageGerman')}</span>
              {germanSelected && <Check className="h-4 w-4 text-indigo-600" aria-hidden />}
            </>
          ) : 'DE'}
          <ChevronDown className={clsx('inline h-3 w-3 transition-transform', germanOpen && 'rotate-180')} aria-hidden />
        </button>
        {germanOpen && (
          <div
            ref={submenuRef}
            id={submenuId}
            role="menu"
            aria-label={t('languageGerman')}
            onKeyDown={onSubmenuKeyDown}
            className={menu ? 'ml-6 border-l border-slate-200' : isLogin ? loginStyles.languageMenu
              : 'absolute right-0 top-full z-[70] mt-2 w-60 rounded-lg border border-slate-200 bg-white py-1 shadow-xl'}
          >
            {LOCALES.filter(loc => loc.code === 'de' || loc.code === 'de-CH').map(loc => (
              <button
                key={loc.code}
                type="button"
                role="menuitemradio"
                aria-checked={locale === loc.code}
                disabled={isPending}
                onClick={() => select(loc.code)}
                title={t(loc.translationKey)}
                className={isLogin ? loginStyles.languageMenuOption : itemClass}
              >
                <span className="w-12 flex-shrink-0 text-xs font-semibold">{loc.label}</span>
                <span className="flex-1">{t(loc.translationKey)}</span>
                {locale === loc.code && <Check className="h-4 w-4" aria-hidden />}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function LanguageSwitcher({ variant = 'default' }: { variant?: 'default' | 'login' }) {
  return <LanguageOptions variant={variant} />;
}
