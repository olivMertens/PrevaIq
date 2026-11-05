// Dates of timeline events: parsing of extracted dates and compact display.
// Pure module (no imports) so tests can load it without the Next.js toolchain.

/** Date in a document field: ISO (2026-08-28), European (28/08/2026, 28.08.2026, 28-08-2026), "2026-08" or "2026". */
export function parseTimelineDate(text: string): Date | null {
  const value = String(text || '');
  let match = value.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));

  match = value.match(/\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b/);
  if (match) {
    const day = Number(match[1]);
    const month = Number(match[2]);
    if (day >= 1 && day <= 31 && month >= 1 && month <= 12) {
      return new Date(Number(match[3]), month - 1, day);
    }
  }

  match = value.match(/(\d{4})-(\d{2})/);
  if (match) return new Date(Number(match[1]), Number(match[2]) - 1, 1);

  match = value.match(/\b(\d{4})\b/);
  if (match) return new Date(Number(match[1]), 0, 1);
  return null;
}

/** Day and month in the reader's language ("Aug 28", "28 août", "28. Aug.") and the year. */
export function formatTimelineDate(date: Date | null, locale: string): { date: string; year: string } {
  if (!date) return { date: '—', year: '' };
  return {
    date: new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }).format(date),
    year: String(date.getFullYear()),
  };
}
