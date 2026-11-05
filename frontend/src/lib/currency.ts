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
