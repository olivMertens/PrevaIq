'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown, Coins } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { CURRENCIES, isCurrencyCode } from '@/lib/currency';
import { useReferenceCurrency } from '@/lib/CurrencyProvider';
import loginStyles from './auth/login.module.css';

export function CurrencyOptions({ onSelected }: { onSelected?: () => void } = {}) {
  const t = useTranslations('currency');
  const { currency, setCurrency } = useReferenceCurrency();
  return (
    <div role="group" aria-label={t('title')}>
      {CURRENCIES.map(code => (
        <button
          key={code}
          type="button"
          role="menuitemradio"
          aria-checked={currency === code}
          onClick={() => { setCurrency(code); onSelected?.(); }}
          className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 focus:bg-slate-100"
        >
          <span className="w-12 flex-shrink-0 text-xs font-semibold text-slate-500">{code}</span>
          <span className="flex-1">{t(code)}</span>
          {currency === code && <Check className="h-4 w-4 text-indigo-600" aria-hidden />}
        </button>
      ))}
      <p className="px-3 py-2 text-xs text-slate-500">{t('referenceHint')}</p>
    </div>
  );
}

export default function CurrencySwitcher({ variant = 'default' }: { variant?: 'default' | 'login' }) {
  const t = useTranslations('currency');
  const { currency, setCurrency } = useReferenceCurrency();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
    const closeOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', closeOutside);
    return () => document.removeEventListener('mousedown', closeOutside);
  }, [open]);
  const close = () => { setOpen(false); triggerRef.current?.focus(); };
  if (variant !== 'login') return (
    <div ref={containerRef} className="relative">
      <button ref={triggerRef} type="button" aria-label={`${t('title')}: ${currency}`}
        aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
        onClick={() => setOpen(value => !value)}
        onKeyDown={event => {
          if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); }
        }}
        className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600">
        <Coins className="h-4 w-4 text-slate-500" aria-hidden />
        <span className="hidden sm:inline">{t('selectorLabel')}</span>
        <span className="font-semibold">{currency}</span>
        <ChevronDown className="h-3.5 w-3.5" aria-hidden />
      </button>
      {open && <div ref={menuRef} id={menuId} role="menu" aria-label={t('title')}
        className="absolute right-0 top-full z-[70] mt-2 w-64 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white py-1 shadow-xl"
        onKeyDown={event => {
          if (event.key === 'Escape') { event.preventDefault(); close(); }
          else if (event.key === 'Tab') setOpen(false);
          else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
            event.preventDefault();
            const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') ?? []);
            const current = items.indexOf(document.activeElement as HTMLButtonElement);
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
              : (current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
            items[next]?.focus();
          }
        }}>
        <p className="px-3 py-2 text-xs font-semibold text-slate-500">{t('title')}</p>
        <CurrencyOptions onSelected={close} />
      </div>}
    </div>
  );
  return (
    <select
      data-currency
      value={currency}
      aria-label={t('title')}
      title={t('referenceHint')}
      onChange={event => {
        const next = event.target.value;
        if (!isCurrencyCode(next)) throw new Error(`Unsupported reference currency: ${next}`);
        setCurrency(next);
      }}
      className={loginStyles.currencySelect}
    >
      {CURRENCIES.map(code => (
        <option key={code} value={code} aria-label={`${code} - ${t(code)}`} data-description={t(code)}>
          {code}
        </option>
      ))}
    </select>
  );
}
