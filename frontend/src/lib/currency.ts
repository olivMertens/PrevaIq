/** Amount display in the currency of a claim (EUR in France, CHF in Switzerland). */

export type CurrencyCode = 'EUR' | 'CHF';

/** Currency of an application, as detected by the backend; EUR when unknown. */
export function applicationCurrency(application?: { jurisdiction?: { currency?: string } } | null): CurrencyCode {
  return application?.jurisdiction?.currency === 'CHF' ? 'CHF' : 'EUR';
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
