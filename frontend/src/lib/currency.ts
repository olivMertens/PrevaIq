/** Amount display without foreign-exchange conversion. */

export const CURRENCIES = ['USD', 'EUR', 'CHF'] as const;
export type CurrencyCode = typeof CURRENCIES[number];
export const CURRENCY_COOKIE = 'reference-currency';

export function isCurrencyCode(value: string | undefined): value is CurrencyCode {
  return CURRENCIES.some(code => code === value);
}

export function resolveReferenceCurrency(value: string | undefined): CurrencyCode {
  return isCurrencyCode(value) ? value : 'EUR';
}

/** An explicit case currency always takes precedence over the user's reference currency. */
export function applicationCurrency(
  application?: { jurisdiction?: { currency?: string } } | null,
  referenceCurrency: CurrencyCode = 'EUR',
): CurrencyCode {
  const currency = application?.jurisdiction?.currency;
  return isCurrencyCode(currency) ? currency : referenceCurrency;
}

/**
 * Format an amount in the UI language. CHF uses Swiss grouping ("CHF 1’697’400"),
 * EUR the UI locale ("1 697 400 €", "€1,697,400").
 */
export function formatAmount(
  value: number,
  currency: CurrencyCode,
  locale: string,
  options: { maximumFractionDigits?: number } = {},
): string {
  const formatLocale = currency === 'CHF' ? `${locale.split('-')[0]}-CH` : locale;
  return new Intl.NumberFormat(formatLocale, { style: 'currency', currency, ...options }).format(value);
}

/** Parse an amount such as "6560 EUR", "10 825 €", "CHF 1'697'400.00" or "6,560.00" (NaN if absent). */
export function parseAmount(raw: string): number {
  const cleaned = String(raw || '').replace(/[^\d.,]/g, '');
  if (!cleaned) return NaN;
  const lastSeparator = Math.max(cleaned.lastIndexOf(','), cleaned.lastIndexOf('.'));
  const decimals = lastSeparator >= 0 ? cleaned.length - lastSeparator - 1 : 0;
  if (lastSeparator >= 0 && decimals > 0 && decimals <= 2) {
    const integer = cleaned.slice(0, lastSeparator).replace(/[.,]/g, '');
    return Number(`${integer}.${cleaned.slice(lastSeparator + 1)}`);
  }
  return Number(cleaned.replace(/[.,]/g, ''));
}
