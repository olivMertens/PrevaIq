// AI analysis outputs (structured JSON) rendered as readable Markdown, and the split of
// that text into the cockpit's summary tabs.
// Pure module (no imports) so tests can load it without the Next.js toolchain.

export type SyntheseTabKey = 'overview' | 'damages' | 'decision' | 'risk' | 'timeline';

// Section headings are routed to a tab by keyword (first matching tab wins).
export const TAB_KEYWORDS: Record<SyntheseTabKey, string[]> = {
  overview: ['vue', 'synthèse', 'synthese', 'résumé', 'resume', 'summary', 'overview', 'contexte', 'dossier', 'assuré', 'assure', 'sinistre'],
  damages: ['dommage', 'préjudice', 'prejudice', 'bien', 'mobilier', 'immobilier', 'damage'],
  decision: ['décision', 'decision', 'couverture', 'recommandation', 'indemnisation', 'franchise', 'garantie', 'coverage', 'verdict', 'settlement', 'payout', 'deductible', 'indemn'],
  risk: ['risque', 'risk', 'fraude', 'fraud', 'alerte', 'alert', 'indicateur', 'signal', 'anomalie', 'consistency', 'suspicious'],
  timeline: ['chronologie', 'timeline', 'historique', 'date', 'événement', 'evenement'],
};

/** Separator between two analyses in the full text (dropped from the topic tabs). */
export const ANALYSIS_SEPARATOR = '\n\n---\n\n';

/** Split the full AI analysis into topic tabs, following its section headings. */
export function parseAiSummary(text: string): Record<SyntheseTabKey, string> {
  const out: Record<SyntheseTabKey, string[]> = {
    overview: [], damages: [], decision: [], risk: [], timeline: [],
  };
  let currentTab: SyntheseTabKey = 'overview';
  for (const line of text ? text.split('\n') : []) {
    const trimmed = line.trim();
    if (trimmed === '---') continue;
    // Markdown headings, or short lines ending with ":" (e.g. "Décision :")
    const heading = trimmed.match(/^#{1,6}\s+(.+)$/);
    if (heading || (trimmed.length > 0 && trimmed.length < 60 && trimmed.endsWith(':'))) {
      const header = (heading ? heading[1] : trimmed).replace(/[:\s]+$/, '').toLowerCase();
      const matched = (Object.entries(TAB_KEYWORDS) as [SyntheseTabKey, string[]][])
        .find(([, keywords]) => keywords.some((keyword) => header.includes(keyword)));
      if (matched) currentTab = matched[0];
    }
    out[currentTab].push(line);
  }
  return Object.fromEntries(
    Object.entries(out).map(([tab, lines]) => [tab, lines.join('\n').trim()]),
  ) as Record<SyntheseTabKey, string>;
}

export interface FieldMarkdownOptions {
  /** Translated label of a known field, or null to derive one from the key. */
  label?: (key: string) => string | null;
  /** Format of monetary amounts (currency and locale of the case). */
  money?: (value: number) => string;
  yes?: string;
  no?: string;
}

const ACRONYMS: Record<string, string> = {
  avb: 'AVB', avo: 'AVO', cg: 'CG', dde: 'DDE', dti: 'DTI', gvz: 'GVZ', hcsf: 'HCSF', id: 'ID',
  irsi: 'IRSI', kpi: 'KPI', ltv: 'LTV', ptz: 'PTZ', rc: 'RC', siu: 'SIU', vvg: 'VVG',
};
const KEY_LABELS: Record<string, string> = { cat_nat: 'Cat-Nat', catnat: 'Cat-Nat' };
const MONEY_KEY = /montant|franchise|indemni|plafond|total|amount|deductible|payout|cost|premium|limit|betrag|selbstbehalt|entsch/i;
const NOT_MONEY_KEY = /count|number|nombre|rate|ratio|percent|score|days|jours|confidence/i;
const ENUM_TOKEN = /^[a-z]+(?:_[a-z]+)+$/;
const INLINE_LIST_MAX = 160;

/** "coverage_status" -> "Coverage status", "irsi" -> "IRSI", "cat_nat" -> "Cat-Nat". */
export function humanizeFieldKey(key: string): string {
  const special = KEY_LABELS[key.toLowerCase()];
  if (special) return special;
  return key
    .replace(/([a-zà-ÿ])([A-Z])/g, '$1 $2')
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word, index) => {
      const acronym = ACRONYMS[word.toLowerCase()];
      if (acronym) return acronym;
      const lower = word.toLowerCase();
      return index === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(' ');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** First non-empty line of a Markdown text as plain text, cut at a word boundary. */
export function markdownPreview(text: string, max = 80): string {
  const line = String(text || '')
    .split('\n')
    .map((part) => part.replace(/^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)/, '').trim())
    .find((part) => part !== '' && part !== '---') ?? '';
  const plain = line
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\*\*|__|`/g, '')
    .replace(/\*(\S[^*]*?)\*/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
  if (plain.length <= max) return plain;
  const cut = plain.slice(0, max - 1);
  const space = cut.lastIndexOf(' ');
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,;:.–—-]+$/, '')}…`;
}

function labelFor(key: string, options: FieldMarkdownOptions): string {
  return options.label?.(key) ?? humanizeFieldKey(key);
}

/** Display text of a scalar value, or null for empty values and containers. */
function scalarText(key: string, value: unknown, options: FieldMarkdownOptions): string | null {
  if (typeof value === 'boolean') return value ? options.yes ?? 'Yes' : options.no ?? 'No';
  if (typeof value === 'number') {
    return options.money && MONEY_KEY.test(key) && !NOT_MONEY_KEY.test(key) ? options.money(value) : String(value);
  }
  if (typeof value !== 'string') return null;
  // One line per field: line breaks inside a value would break the Markdown list.
  const text = value.replace(/\s*\n\s*/g, ' ').trim();
  if (!text) return null;
  return ENUM_TOKEN.test(text) ? humanizeFieldKey(text) : text;
}

function objectLines(obj: Record<string, unknown>, depth: number, options: FieldMarkdownOptions): string[] {
  return Object.entries(obj)
    .filter(([key]) => !key.startsWith('_'))
    .flatMap(([key, value]) => fieldLines(key, value, depth, options));
}

/** An object in a list: its first value as the item title, its other fields below. */
function itemLines(key: string, item: unknown, depth: number, options: FieldMarkdownOptions): string[] {
  const indent = '  '.repeat(depth);
  if (!isRecord(item)) {
    const text = scalarText(key, item, options);
    return text ? [`${indent}- ${text}`] : [];
  }
  const entries = Object.entries(item).filter(([field]) => !field.startsWith('_'));
  const titleIndex = entries.findIndex(([field, value]) => scalarText(field, value, options) !== null);
  if (titleIndex < 0) return objectLines(item, depth, options);
  const [titleKey, titleValue] = entries[titleIndex];
  const rest = Object.fromEntries(entries.filter((_, index) => index !== titleIndex));
  return [`${indent}- **${scalarText(titleKey, titleValue, options)}**`, ...objectLines(rest, depth + 1, options)];
}

function fieldLines(key: string, value: unknown, depth: number, options: FieldMarkdownOptions): string[] {
  const indent = '  '.repeat(depth);
  const label = labelFor(key, options);
  const scalar = scalarText(key, value, options);
  if (scalar !== null) return [`${indent}- **${label}:** ${scalar}`];
  if (Array.isArray(value)) {
    const items = value.filter((item) => item !== null && item !== undefined && item !== '');
    if (items.length === 0) return [];
    const texts = items.map((item) => scalarText(key, item, options));
    if (texts.every((text) => text !== null)) {
      const joined = texts.join(', ');
      if (joined.length <= INLINE_LIST_MAX) return [`${indent}- **${label}:** ${joined}`];
      return [`${indent}- **${label}:**`, ...texts.map((text) => `${indent}  - ${text}`)];
    }
    const children = items.flatMap((item) => itemLines(key, item, depth + 1, options));
    return children.length > 0 ? [`${indent}- **${label}:**`, ...children] : [];
  }
  if (isRecord(value)) {
    const children = objectLines(value, depth + 1, options);
    return children.length > 0 ? [`${indent}- **${label}:**`, ...children] : [];
  }
  return [];
}

/**
 * Markdown of a structured analysis: simple fields as a list, each nested object or
 * list under its own heading (headings also route the text to the summary tabs).
 */
export function analysisFieldsMarkdown(parsed: Record<string, unknown>, options: FieldMarkdownOptions = {}): string {
  const blocks: string[] = [];
  let simpleFields: string[] = [];
  const flush = () => {
    if (simpleFields.length > 0) blocks.push(simpleFields.join('\n'));
    simpleFields = [];
  };
  for (const [key, value] of Object.entries(parsed)) {
    if (key.startsWith('_')) continue;
    const lines = fieldLines(key, value, 0, options);
    if (lines.length === 0) continue;
    if (lines.length === 1) {
      simpleFields.push(lines[0]);
      continue;
    }
    flush();
    // The "- **Label:**" line becomes a heading; its children move up one level.
    blocks.push([`#### ${labelFor(key, options)}`, ...lines.slice(1).map((line) => line.slice(2))].join('\n'));
  }
  flush();
  return blocks.join('\n\n');
}
