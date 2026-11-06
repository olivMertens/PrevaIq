// The open case in the address bar (?app=…&persona=…&view=…&page=…), so that a reload —
// the language switch reloads the page — reopens the same case, tab and page.
// Pure helpers (no imports) plus one browser-only writer.

export const CASE_VIEWS = ['overview', 'timeline', 'documents', 'source', 'analysis', 'customer', 'weather', 'data', 'pipeline'] as const;
export type CaseView = (typeof CASE_VIEWS)[number];

export type CaseParams = Partial<Record<'app' | 'persona' | 'view' | 'page' | 'conversation', string | number | null>>;

/** Query string with the given parameters set, or removed when null or empty. */
export function withCaseParams(search: string, params: CaseParams): string {
  const query = new URLSearchParams(search);
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') query.delete(key);
    else query.set(key, String(value));
  }
  const text = query.toString();
  return text ? `?${text}` : '';
}

/** Case, tab and page to reopen, as written by {@link writeCaseParams}. */
export function readCaseParams(search: string) {
  const query = new URLSearchParams(search);
  const view = query.get('view');
  const page = Number(query.get('page'));
  return {
    app: query.get('app'),
    persona: query.get('persona'),
    conversation: query.get('conversation'),
    view: (CASE_VIEWS as readonly string[]).includes(view ?? '') ? (view as CaseView) : null,
    page: Number.isInteger(page) && page > 0 ? page : null,
  };
}

/** Updates the address bar in place: no navigation and no new history entry. */
export function writeCaseParams(params: CaseParams): void {
  if (typeof window === 'undefined') return;
  const { pathname, search, hash } = window.location;
  const next = withCaseParams(search, params);
  if (next !== search) window.history.replaceState(null, '', `${pathname}${next}${hash}`);
}
