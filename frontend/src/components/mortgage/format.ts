/**
 * Shared formatting utilities for mortgage components.
 */

/**
 * Format a number as EUR currency (e.g. "125 000 €").
 * Returns "—" for null/undefined values.
 */
export function formatCurrency(amount: number | null | undefined, locale = 'en'): string {
  if (amount == null) return '—';
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format a number with locale grouping (e.g. "1 250").
 * Returns "—" for null/undefined values.
 */
export function formatNumber(value: number | null | undefined, decimals = 0, locale = 'en'): string {
  if (value == null) return '—';
  return new Intl.NumberFormat(locale, { maximumFractionDigits: decimals }).format(value);
}

/**
 * Format a ratio as a percentage string.
 * Expects the value to already be in percentage form (e.g. 26.36 → "26.36%").
 * Returns "N/A" for non-finite values.
 */
export function formatPercent(value: number, decimals = 2, locale = 'en'): string {
  if (!isFinite(value)) return 'N/A';
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value / 100);
}

/**
 * Format a 0–1 ratio as percentage (e.g. 0.2636 → "26.36%").
 */
export function formatRatio(value: number, decimals = 2, locale = 'en'): string {
  if (!isFinite(value)) return 'N/A';
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * Format a signed percentage with +/- prefix (e.g. +2.5%, -1.3%).
 * Returns "—" for null/undefined values.
 */
export function formatSignedPercent(value: number | null | undefined, decimals = 1, locale = 'en'): string {
  if (value == null) return '—';
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    signDisplay: 'always',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value / 100);
}

/** Severity → Tailwind text color class */
export function getStatusColor(status: 'pass' | 'warning' | 'fail'): string {
  switch (status) {
    case 'pass': return 'text-green-600';
    case 'warning': return 'text-amber-600';
    case 'fail': return 'text-red-600';
  }
}

/** Severity → Tailwind bg + border classes */
export function getStatusBg(status: 'pass' | 'warning' | 'fail'): string {
  switch (status) {
    case 'pass': return 'bg-green-50 border-green-200';
    case 'warning': return 'bg-amber-50 border-amber-200';
    case 'fail': return 'bg-red-50 border-red-200';
  }
}
