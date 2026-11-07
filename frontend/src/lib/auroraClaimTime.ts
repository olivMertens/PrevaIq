export function parseAuroraClaimTime(value?: string): {
  start: number; end: number; marker: number; precision: 'day' | 'instant';
} | null {
  if (!value) return null;
  const iso = value.match(/^(\d{4})-(\d{2})-(\d{2})(.*)$/);
  const european = value.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (!iso && !european) return null;
  const year = Number(iso ? iso[1] : european![3]);
  const month = Number(iso ? iso[2] : european![2]);
  const day = Number(iso ? iso[3] : european![1]);
  const calendar = new Date(Date.UTC(year, month - 1, day));
  if (calendar.getUTCFullYear() !== year || calendar.getUTCMonth() !== month - 1 || calendar.getUTCDate() !== day) return null;
  if (iso?.[4]) {
    if (!/^T\d{2}:\d{2}/.test(iso[4]) || !/(Z|[+-]\d{2}:\d{2})$/.test(iso[4])) return null;
    const timestamp = Date.parse(value);
    return Number.isNaN(timestamp) ? null : {start: timestamp, end: timestamp, marker: timestamp, precision: 'instant'};
  }
  const start = new Date(year, month - 1, day).getTime();
  const end = new Date(year, month - 1, day + 1).getTime() - 1;
  return {start, end, marker: new Date(year, month - 1, day, 12).getTime(), precision: 'day'};
}
