'use client';

import Link from 'next/link';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown, CircleHelp, LogOut, Settings, User } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import DemoGuideModal from './DemoGuideModal';
import { LOCALES, useLocaleSwitch } from './LanguageSwitcher';

const LANGUAGE_KEYS = { en: 'languageEnglish', fr: 'languageFrench', de: 'languageGerman' } as const;
const ITEM_CLASS =
  'flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 focus:bg-slate-100 focus:outline-none disabled:opacity-50';

interface UserMenuProps {
  /** Full identity (e-mail), null when unknown. */
  user: string | null;
  /** Short identity shown in the header on wide screens. */
  userLabel: string | null;
  canAdmin: boolean;
  /** Absent when authentication is disabled. */
  onSignOut?: () => void;
}

/** Account menu: language, demo guide, administration and sign-out, out of the header bar. */
export default function UserMenu({ user, userLabel, canAdmin, onSignOut }: UserMenuProps) {
  const t = useTranslations('nav');
  const tAuth = useTranslations('auth');
  const tDemo = useTranslations('demoGuide');
  const { locale, isPending, switchLocale } = useLocaleSwitch();
  const [open, setOpen] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>('[aria-checked="true"], [role^="menuitem"]')?.focus();
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  const onMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]') ?? []);
    const index = items.indexOf(document.activeElement as HTMLElement);
    const focusAt = (next: number) => items[(next + items.length) % items.length]?.focus();
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'Tab') {
      setOpen(false);
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      focusAt(index + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      focusAt(index - 1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      focusAt(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      focusAt(items.length - 1);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={t('userMenu')}
        title={user ?? t('userMenu')}
        className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
      >
        <User className="h-4 w-4" aria-hidden />
        {userLabel && <span className="hidden max-w-36 truncate xl:inline">{userLabel}</span>}
        <span className="text-xs font-semibold text-slate-500">{locale.toUpperCase()}</span>
        <ChevronDown className={clsx('h-4 w-4 text-slate-400 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>

      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={t('userMenu')}
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 top-full z-[60] mt-2 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-xl"
        >
          {user && (
            <p className="truncate border-b border-slate-100 px-3 py-2 text-xs text-slate-500" title={user}>
              {t('signedInAs', { user })}
            </p>
          )}
          <p id={`${menuId}-language`} className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {tAuth('languageLabel')}
          </p>
          <div role="group" aria-labelledby={`${menuId}-language`}>
            {LOCALES.map((option) => (
              <button
                key={option.code}
                type="button"
                role="menuitemradio"
                aria-checked={locale === option.code}
                disabled={isPending}
                onClick={() => (option.code === locale ? close() : switchLocale(option.code))}
                className={ITEM_CLASS}
              >
                <span className="w-6 text-xs font-semibold text-slate-500">{option.label}</span>
                <span className="flex-1">{tAuth(LANGUAGE_KEYS[option.code])}</span>
                {locale === option.code && <Check className="h-4 w-4 text-indigo-600" aria-hidden />}
              </button>
            ))}
          </div>
          <div role="separator" className="my-1 border-t border-slate-100" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              setDemoOpen(true);
            }}
            className={ITEM_CLASS}
          >
            <CircleHelp className="h-4 w-4 text-slate-500" aria-hidden />
            {tDemo('openTitle')}
          </button>
          {canAdmin && (
            <Link href="/admin" role="menuitem" onClick={() => setOpen(false)} className={ITEM_CLASS}>
              <Settings className="h-4 w-4 text-slate-500" aria-hidden />
              {t('admin')}
            </Link>
          )}
          {onSignOut && (
            <>
              <div role="separator" className="my-1 border-t border-slate-100" />
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onSignOut();
                }}
                className={ITEM_CLASS}
              >
                <LogOut className="h-4 w-4 text-slate-500" aria-hidden />
                {t('signOut')}
              </button>
            </>
          )}
        </div>
      )}

      <DemoGuideModal open={demoOpen} onOpenChange={setDemoOpen} />
    </div>
  );
}
