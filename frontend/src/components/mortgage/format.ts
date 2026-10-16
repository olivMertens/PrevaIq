/**
 * Shared formatting utilities for mortgage components.
 */

/**
 * Format a number as EUR currency (e.g. "125 000 €").
 * Returns "—" for null/undefined values.
 */
export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null) return '—';
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format a number with locale grouping (e.g. "1 250").
 * Returns "—" for null/undefined values.
 */
export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: decimals }).format(value);
}

/**
 * Format a ratio as a percentage string.
 * Expects the value to already be in percentage form (e.g. 26.36 → "26.36%").
 * Returns "N/A" for non-finite values.
 */
export function formatPercent(value: number, decimals = 2): string {
  if (!isFinite(value)) return 'N/A';
  return `${value.toFixed(decimals)}%`;
}

/**
 * Format a 0–1 ratio as percentage (e.g. 0.2636 → "26.36%").
 */
export function formatRatio(value: number, decimals = 2): string {
  if (!isFinite(value)) return 'N/A';
  return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * Format a signed percentage with +/- prefix (e.g. +2.5%, -1.3%).
 * Returns "—" for null/undefined values.
 */
export function formatSignedPercent(value: number | null | undefined, decimals = 1): string {
  if (value == null) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`;
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
