'use client';

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { applicationCurrency, CURRENCY_COOKIE, type CurrencyCode } from '@/lib/currency';

interface CurrencyContextValue {
  currency: CurrencyCode;
  setCurrency: (currency: CurrencyCode) => void;
}

const CurrencyContext = createContext<CurrencyContextValue | null>(null);

export function CurrencyProvider({ initialCurrency, children }: { initialCurrency: CurrencyCode; children: ReactNode }) {
  const [currency, setCurrentCurrency] = useState(initialCurrency);
  const setCurrency = useCallback((next: CurrencyCode) => {
    document.cookie = `${CURRENCY_COOKIE}=${next};path=/;max-age=31536000;samesite=lax`;
    setCurrentCurrency(next);
  }, []);
  return <CurrencyContext.Provider value={{ currency, setCurrency }}>{children}</CurrencyContext.Provider>;
}

export function useReferenceCurrency() {
  const context = useContext(CurrencyContext);
  if (!context) throw new Error('useReferenceCurrency must be used within a CurrencyProvider');
  return context;
}

export function useApplicationCurrency(application?: Parameters<typeof applicationCurrency>[0]) {
  const { currency } = useReferenceCurrency();
  return applicationCurrency(application, currency);
}
