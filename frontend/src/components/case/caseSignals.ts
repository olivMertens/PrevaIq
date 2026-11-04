// Case cockpit signals: every fact shows up once, the most important first.
// Pure module (no imports) so tests can load it without the Next.js toolchain.

export type SignalSeverity = 'critical' | 'warning' | 'info';

export type SignalTheme =
  | 'photos'
  | 'statement'
  | 'timeline'
  | 'cover'
  | 'amount'
  | 'policy'
  | 'fraud'
  | 'documents'
  | 'customer';

export type SignalSource =
  | 'photoAnalysis'
  | 'declarationCheck'
  | 'fraudModel'
  | 'webIq'
  | 'policy'
  | 'rule'
  | 'fileDates'
  | 'aiAnalysis';

export type DeepDiveTab =
  | 'summary'
  | 'fraud'
  | 'web'
  | 'cover'
  | 'evidence'
  | 'customer'
  | 'timeline'
  | 'data'
  | 'pipeline';

export type SignalFilter = 'all' | 'fraud' | 'cover' | 'amount' | 'documents' | 'customer';

export interface RawSignal {
  theme: SignalTheme;
  severity: SignalSeverity;
  title: string;
  detail: string;
  sources: SignalSource[];
  tab?: DeepDiveTab;
  sourceUrl?: string;
}

export interface CaseSignal {
  id: string;
  theme: SignalTheme;
  severity: SignalSeverity;
  title: string;
  detail: string;
  sources: SignalSource[];
  tab: DeepDiveTab;
  sourceUrl?: string;
  /** Titles of the other signals merged into this one, kept for traceability. */
  merged: string[];
}

export const SEVERITY_RANK: Record<SignalSeverity, number> = { critical: 0, warning: 1, info: 2 };

const THEME_ORDER: SignalTheme[] = [
  'photos', 'statement', 'timeline', 'cover', 'amount', 'policy', 'fraud', 'documents', 'customer',
];

export const THEME_TAB: Record<SignalTheme, DeepDiveTab> = {
  photos: 'evidence',
  statement: 'fraud',
  timeline: 'timeline',
  cover: 'web',
  amount: 'cover',
  policy: 'cover',
  fraud: 'fraud',
  documents: 'evidence',
  customer: 'customer',
};

export const THEME_FILTER: Record<SignalTheme, SignalFilter> = {
  photos: 'fraud',
  statement: 'fraud',
  timeline: 'fraud',
  fraud: 'fraud',
  cover: 'cover',
  policy: 'cover',
  amount: 'amount',
  documents: 'documents',
  customer: 'customer',
};

// Free-text findings from the models (EN/FR/DE) are filed under a theme from their title.
const THEME_HINTS: Array<[SignalTheme, RegExp]> = [
  ['photos', /\b(photos?|images?|pictures?|bild|bilder|fotos?|visuel|visuals?|synth|ai[- ]generated|généré|manipul)/i],
  ['timeline', /(chronolog|timeline|temporal|temporel|dated|daté|datum|zeitlich|zeitpunkt|horodat)/i],
  ['statement', /(statement|déclaration|declaration|consisten|konsisten|cohéren|concordan|schadenmeldung|aussage|widerspr)/i],
  ['cover', /(weather|météo|meteo|wetter|storm|tempête|tempete|cat-?nat|catastrophe|sturm|hagel|grêle|grele|rain|pluie|regen)/i],
  ['amount', /(amount|montant|betrag|cost|coût|cout|kosten|€|chf|estimat|devis|schätz)/i],
  ['policy', /(exclusion|cover|couverture|garantie|polic|deductible|franchise|deckung|ausschl|selbstbehalt)/i],
  ['documents', /(document|missing|manquant|pièce|piece|fehlend|unterlage)/i],
  ['customer', /(customer|client|kunde|urgen|stress|sentiment)/i],
];

/** File a model finding under a theme from its title; unknown findings stay "fraud". */
export function classifyTheme(title: string, fallback: SignalTheme = 'fraud'): SignalTheme {
  for (const [theme, pattern] of THEME_HINTS) {
    if (pattern.test(title)) return theme;
  }
  return fallback;
}

// Unclassified model findings are distinct issues: never collapse them together.
const NEVER_MERGED: ReadonlySet<SignalTheme> = new Set<SignalTheme>(['fraud']);

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

/** Merge signals that describe the same theme, keep the strongest wording, rank the result. */
export function mergeSignals(raw: RawSignal[]): CaseSignal[] {
  const groups = new Map<string, CaseSignal>();
  raw.forEach((signal, index) => {
    const key = NEVER_MERGED.has(signal.theme) ? `${signal.theme}-${index}` : signal.theme;
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, {
        id: key,
        theme: signal.theme,
        severity: signal.severity,
        title: signal.title,
        detail: signal.detail,
        sources: unique(signal.sources),
        tab: signal.tab ?? THEME_TAB[signal.theme],
        sourceUrl: signal.sourceUrl,
        merged: [],
      });
      return;
    }
    const sources = unique([...existing.sources, ...signal.sources]);
    if (SEVERITY_RANK[signal.severity] < SEVERITY_RANK[existing.severity]) {
      groups.set(key, {
        ...existing,
        severity: signal.severity,
        title: signal.title,
        detail: signal.detail,
        tab: signal.tab ?? existing.tab,
        sourceUrl: signal.sourceUrl ?? existing.sourceUrl,
        sources,
        merged: unique([existing.title, ...existing.merged]).filter((title) => title !== signal.title),
      });
      return;
    }
    existing.sources = sources;
    existing.sourceUrl = existing.sourceUrl ?? signal.sourceUrl;
    if (signal.title !== existing.title && !existing.merged.includes(signal.title)) {
      existing.merged.push(signal.title);
    }
  });
  return Array.from(groups.values()).sort(
    (a, b) =>
      SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
      THEME_ORDER.indexOf(a.theme) - THEME_ORDER.indexOf(b.theme),
  );
}

/** Number of signals per filter, for the filter chips ("Fraud 3", "Cover 1"...). */
export function countByFilter(signals: CaseSignal[]): Record<SignalFilter, number> {
  const counts: Record<SignalFilter, number> = {
    all: signals.length, fraud: 0, cover: 0, amount: 0, documents: 0, customer: 0,
  };
  for (const signal of signals) counts[THEME_FILTER[signal.theme]] += 1;
  return counts;
}

/** Essential view: critical and warning signals first, capped; the rest stays one click away. */
export function splitEssential(signals: CaseSignal[], limit = 5): { shown: CaseSignal[]; hidden: CaseSignal[] } {
  const important = signals.filter((signal) => signal.severity !== 'info');
  const shown = important.slice(0, limit);
  const shownIds = new Set(shown.map((signal) => signal.id));
  return { shown, hidden: signals.filter((signal) => !shownIds.has(signal.id)) };
}
