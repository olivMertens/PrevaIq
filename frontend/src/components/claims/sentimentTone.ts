/**
 * Shared sentiment → tone mapping.
 *
 * The same sentiment signal that powers `ClientSentimentPanel` (Accompagnement
 * client recommendation card) also drives the color of the Communication
 * client banner — so a "Normal" / "Serein" client doesn't see an alarming red
 * banner. Severity is derived from the backend `sentiment_analysis` payload
 * (preferred), with a numeric score fallback.
 */


export type Severity = 'critical' | 'warning' | 'normal' | 'serene';

export interface SeverityTone {
  /** Accent color for icons and titles (Tailwind class). */
  iconColor: string;
  /** Filled tinted background + border for the primary CTA button. */
  buttonClass: string;
  /** Optional subtle banner background — currently kept slate for visual calm. */
  badgeBg: string;
  badgeText: string;
  label: string;
}

/**
 * Map a backend sentiment level / score to a normalized severity. Matches the
 * thresholds in `ClientSentimentPanel.levelToVisual` so the two surfaces stay
 * in sync.
 */
export function severityFromSentiment(
  sentiment?: { level?: string; score?: number } | null,
): Severity {
  if (!sentiment) return 'normal';
  const level = sentiment.level || '';
  const score = typeof sentiment.score === 'number' ? sentiment.score : 0;
  if (level === 'critical' || score >= 70) return 'critical';
  if (level === 'stressed' || score >= 50) return 'warning';
  if (level === 'moderate' || level === 'concerned' || score >= 30) return 'normal';
  return 'serene';
}

/**
 * Tailwind class palette for a given severity. The "normal" / "serene" tones
 * use calm colors so the banner does not turn red when the AI signals a calm client.
 */
export function toneForSeverity(severity: Severity): SeverityTone {
  switch (severity) {
    case 'critical':
      return {
        iconColor: 'text-rose-700',
        buttonClass:
          'bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100',
        badgeBg: 'bg-rose-100',
        badgeText: 'text-rose-700',
        label: 'Attention requise',
      };
    case 'warning':
      return {
        iconColor: 'text-amber-700',
        buttonClass:
          'bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100',
        badgeBg: 'bg-amber-100',
        badgeText: 'text-amber-700',
        label: 'Vigilance',
      };
    case 'serene':
      return {
        iconColor: 'text-emerald-700',
        buttonClass:
          'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100',
        badgeBg: 'bg-emerald-100',
        badgeText: 'text-emerald-700',
        label: 'Serein',
      };
    case 'normal':
    default: {
      return {
        iconColor: 'text-slate-600',
        buttonClass:
          'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100',
        badgeBg: 'bg-slate-100',
        badgeText: 'text-slate-700',
        label: 'Normal',
      };
    }
  }
}
