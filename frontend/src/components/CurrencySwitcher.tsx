'use client';

import { Check } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { CURRENCIES, isCurrencyCode } from '@/lib/currency';
import { useReferenceCurrency } from '@/lib/CurrencyProvider';
import loginStyles from './auth/login.module.css';

export function CurrencyOptions() {
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
          onClick={() => setCurrency(code)}
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
  return (
    <select
      value={currency}
      aria-label={t('title')}
      title={t('referenceHint')}
      onChange={event => {
        const next = event.target.value;
        if (!isCurrencyCode(next)) throw new Error(`Unsupported reference currency: ${next}`);
        setCurrency(next);
      }}
      className={variant === 'login' ? loginStyles.currencySelect
        : 'rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-semibold text-slate-600'}
    >
      {CURRENCIES.map(code => <option key={code} value={code}>{code}</option>)}
    </select>
  );
}
