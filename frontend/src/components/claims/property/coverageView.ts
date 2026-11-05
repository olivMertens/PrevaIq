// Coverage and settlement analyses turned into the view model of the "Cover & amounts" tab.
// The LLM writes free-form JSON (French or English keys, lists or maps, nested or flat), so
// each fact is looked up among its known names; anything unrecognised stays available in the
// full analysis. Pure module (pure imports only) so tests can load it without Next.js.
import { parseAmount } from '@/lib/currency';

export type CoverageTone = 'covered' | 'partial' | 'review' | 'excluded' | 'notConcerned' | 'unknown';

export type PerilKey =
  | 'water'
  | 'storm'
  | 'hail'
  | 'natural'
  | 'catNat'
  | 'fire'
  | 'liability'
  | 'theft'
  | 'glass'
  | 'electrical';

/** A guarantee, an exclusion or a claim item. */
export interface CoverageEntry {
  name: string;
  /** Known peril of a guarantee, shown with its translated name. */
  peril?: PerilKey;
  tone: CoverageTone;
  reason?: string;
  notes: string[];
  amount?: number;
  /** Policy articles cited for this entry ("AVB Ziff. B1.3"). */
  references: string[];
}

/** A policy article the analysis relied on. */
export interface CoverageCitation {
  /** Article of the policy conditions ("AVB Ziff. B2"), else the policy id. */
  reference: string;
  /** Criteria or policy id ("CH-AVB-ELE-001-B"). */
  id?: string;
  /** Why the article applies, written by the analysis (UI language). */
  why?: string;
  /** Wording quoted from the policy, in the language of the policy. */
  name?: string;
  condition?: string;
  effect?: string;
}

export interface CoverageRule {
  /** true or false when the analysis states it, null otherwise. */
  applies: boolean | null;
  amount?: number;
  detail?: string;
  reason?: string;
}

export interface CoverageArticle {
  reference: string;
  /** Conclusion as written by the analysis ("Applicable", "Not applicable"). */
  status?: string;
  tone: CoverageTone;
  effect?: string;
}

export interface CoverageView {
  tone: CoverageTone;
  summary?: string;
  coveredHighlight?: string;
  notCoveredHighlights: string[];
  event?: { cause?: string; covered: boolean | null };
  amounts: { eligible?: number; deductible?: number; recommended?: number };
  settlementNote?: string;
  lines: CoverageEntry[];
  guarantees: CoverageEntry[];
  exclusionsSummary?: string;
  exclusions: CoverageEntry[];
  attention: string[];
  conditions: string[];
  basis: string[];
  rules: {
    deductible?: CoverageRule;
    catNat?: CoverageRule;
    irsi?: CoverageRule;
    expertise?: CoverageRule;
    recourse?: CoverageRule & { against: string[] };
  };
  /** The coverage check and the settlement apply different deductibles. */
  deductibleMismatch?: { coverage: number; settlement: number };
  articles: CoverageArticle[];
  citations: CoverageCitation[];
  hasContent: boolean;
}

type Rec = Record<string, unknown>;

function isRecord(value: unknown): value is Rec {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function record(value: unknown): Rec | undefined {
  return isRecord(value) ? value : undefined;
}

/** Lower case, no accents, "_" between words: "Statut couverture" -> "statut_couverture". */
function token(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/** First non-empty value among the given key names (compared as tokens), in key order. */
function pick(source: unknown, keys: string[]): unknown {
  if (!isRecord(source)) return undefined;
  const entries = Object.entries(source).map(([key, value]) => [token(key), value] as const);
  for (const key of keys) {
    const match = entries.find(([name, value]) => name === key && value !== null && value !== undefined && value !== '');
    if (match) return match[1];
  }
  return undefined;
}

/** pick() on the object, then on its direct child objects. */
function pickDeep(source: unknown, keys: string[]): unknown {
  const direct = pick(source, keys);
  if (direct !== undefined || !isRecord(source)) return direct;
  for (const child of Object.values(source)) {
    const nested = pick(child, keys);
    if (nested !== undefined) return nested;
  }
  return undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function strings(value: unknown): string[] {
  if (typeof value === 'string') return value.trim() ? [value.trim()] : [];
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => (typeof item === 'string' && item.trim() ? [item.trim()] : []));
}

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

// One amount, possibly with a currency: "CHF 1'697'400.00", "10 825 €" (not a sentence).
const SINGLE_AMOUNT = /^[^\d]{0,6}\d[\d\s'’.,]*[^\d]{0,6}$/;

function amount(value: unknown): number | undefined {
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined;
  if (typeof value !== 'string' || !SINGLE_AMOUNT.test(value.trim())) return undefined;
  const parsed = parseAmount(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/** A code written by the LLM ("third_party_liability"), as opposed to translated text. */
export function isCode(value: string): boolean {
  return /^[a-z0-9]+(?:_[a-z0-9]+)+$/i.test(value);
}

/** Codes read as text: "third_party_liability" -> "Third party liability". */
export function humanizeCode(value: string): string {
  if (!isCode(value)) return value;
  const sentence = value.replace(/_/g, ' ');
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

// ── Statuses ─────────────────────────────────────────────────────────────────

const NOT_CONCERNED = /not_?triggered|not_?concerned|not_?involved|non_?concerne|sans_objet|not_?applicable|non_?applicable|inapplicable|nicht_?anwendbar|nicht_?betroffen|not_?retained|non_?retenu|^n_?a$|^none$|^aucun/;
const PARTIAL = /partiel|partial|teilweise/;
const EXCLUDED = /exclu|ausgeschlossen|not_?covered|non_?couvert|nicht_?gedeckt|refus|denied|rejected|abgelehnt|^(non|no|nein|false)$/;
const REVIEW = /review|a_verifier|to_verify|verification|check|not_?confirmed|non_?confirme|unconfirmed|to_?confirm|a_?confirmer|confirmation|reserve|provisional|provisoire|pending|attention|vigilance|demontre|uncertain|incertain|unclear|a_preciser|to_be|conditional|sous_condition|zu_pruefen|zu_prufen|offen|suspend/;
const COVERED = /covered|couvert|gedeckt|^(oui|yes|ja|true)$|accept|accord|eligible|applicable|anwendbar|retenu|confirmed|confirme|verifie|verified/;

/** Coverage status of a free-form value: true/false, "oui", "partially_covered", "excluded_…". */
export function statusTone(value: unknown): CoverageTone {
  if (value === true) return 'covered';
  if (value === false) return 'excluded';
  const status = typeof value === 'string' ? token(value) : '';
  if (!status) return 'unknown';
  if (NOT_CONCERNED.test(status)) return 'notConcerned';
  if (PARTIAL.test(status)) return 'partial';
  if (EXCLUDED.test(status)) return 'excluded';
  if (REVIEW.test(status)) return 'review';
  if (COVERED.test(status)) return 'covered';
  return 'unknown';
}

/** A peril answered "no" ("no fire described") is not involved; "not covered" stays excluded. */
function guaranteeTone(value: unknown): CoverageTone {
  const tone = statusTone(value);
  if (tone !== 'excluded') return tone;
  return value === false || /^(non|no|nein|false)$/.test(token(String(value))) ? 'notConcerned' : 'excluded';
}

/** An exclusion that applies excludes; an uncertain one is to review. */
function exclusionTone(value: unknown): CoverageTone {
  const tone = statusTone(value);
  if (tone === 'covered') return 'excluded';
  return tone === 'partial' || tone === 'unknown' ? 'review' : tone;
}

/** true / false / null for "applies", "required", "possible" answers. */
function flag(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value;
  const tone = statusTone(value);
  if (tone === 'covered') return true;
  return tone === 'excluded' || tone === 'notConcerned' ? false : null;
}

// ── Perils ───────────────────────────────────────────────────────────────────

const PERILS: Array<[PerilKey, RegExp]> = [
  ['water', /^(dde|degats?_des_eaux|water|wasser|leitungswasser|infiltration)/],
  ['storm', /^(tempete|storm|sturm|wind|ouragan|hurricane)/],
  ['hail', /^(grele|hail|hagel)/],
  ['catNat', /^(cat_?nat|catastrophe)/],
  ['natural', /^(elementar|natural|evenements?_naturels?|naturgefahr)/],
  ['fire', /^(incendie|fire|feuer|brand)/],
  ['liability', /^(rc|responsabilite|liability|third_party_liability|haftpflicht)/],
  ['theft', /^(vol|theft|vandal|diebstahl|cambriolage|burglary|einbruch)/],
  ['glass', /^(bris_de_glace|glass|glas)/],
  ['electrical', /^(dommages?_electriques?|electrical|elektro)/],
];

/** Every peril with a translated name. */
export const PERIL_KEYS: readonly PerilKey[] = PERILS.map(([key]) => key);

/** Known peril of a short guarantee name ("DDE", "tempête", "Third-party liability"). */
export function perilKey(name: string): PerilKey | undefined {
  const key = token(name);
  if (key.length > 24) return undefined;
  return PERILS.find(([, pattern]) => pattern.test(key))?.[0];
}

// ── Policy citations ─────────────────────────────────────────────────────────

const ARTICLE_IN_PARENS = /\(([^()]*\b(?:AVB|CG|CGV|CP|Art|Article|Ziff|Chapitre|Kapitel)\b[^()]*)\)\s*$/i;
const ARTICLE_IN_TEXT = /(?:\b(?:Art|Article|Ziff)\.?|§)\s*\d[\w.]*/i;

function citation(value: unknown): CoverageCitation | null {
  if (!isRecord(value)) return null;
  const id = text(pick(value, ['criteria_id', 'policy_id', 'id']));
  let name = text(pick(value, ['policy_name', 'title', 'titre', 'name', 'nom']));
  let reference = text(pick(value, ['article', 'reference']));
  if (!reference && name) {
    const inParens = name.match(ARTICLE_IN_PARENS);
    if (inParens) {
      reference = inParens[1].trim();
      name = name.slice(0, inParens.index).replace(/[\s—–-]+$/, '').trim() || undefined;
    } else {
      reference = name.match(ARTICLE_IN_TEXT)?.[0];
    }
  }
  reference = reference ?? text(pick(value, ['policy_id'])) ?? id ?? name;
  if (!reference) return null;
  return {
    reference,
    id,
    why: text(pick(value, ['rationale', 'justification', 'reason', 'motif'])),
    name: name && name !== reference ? name : undefined,
    condition: text(pick(value, ['matched_condition', 'condition', 'text', 'citation_text', 'texte'])),
    effect: text(pick(value, ['applied_action', 'action', 'effect', 'effet'])),
  };
}

function isCitation(value: CoverageCitation | null): value is CoverageCitation {
  return value !== null;
}

function citationsOf(value: unknown): CoverageCitation[] {
  const raw = pick(value, ['policy_citations', 'policy_citation', 'citations', 'citation']);
  return (Array.isArray(raw) ? raw : raw ? [raw] : []).map(citation).filter(isCitation);
}

/** Every citation of an analysis, wherever the LLM nested it. */
function allCitations(value: unknown, depth = 0): CoverageCitation[] {
  if (depth > 5) return [];
  if (Array.isArray(value)) return value.flatMap((item) => allCitations(item, depth + 1));
  if (!isRecord(value)) return [];
  return [
    ...citationsOf(value),
    ...Object.entries(value)
      .filter(([key]) => !token(key).includes('citation'))
      .flatMap(([, child]) => allCitations(child, depth + 1)),
  ];
}

function uniqueCitations(citations: CoverageCitation[]): CoverageCitation[] {
  const seen = new Set<string>();
  return citations.filter((item) => {
    const key = item.id ?? `${item.reference}|${item.condition ?? ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ── Entries: guarantees, exclusions, claim items ─────────────────────────────

const NAME_KEYS = ['item', 'risk', 'garantie', 'guarantee', 'peril', 'exclusion', 'poste', 'label', 'name', 'nom', 'titre', 'title', 'risque', 'designation', 'description'];
const STATUS_KEYS = ['coverage_status', 'status', 'statut', 'decision', 'conclusion', 'impact', 'couverture', 'coverage', 'covered', 'couvert', 'applies', 'applicable'];
const REASON_KEYS = ['explanation', 'reason', 'motif', 'rationale', 'justification', 'commentaire', 'comment', 'details', 'detail', 'explication'];
const NOTE_KEYS = ['observations', 'notes', 'remarks', 'remarques'];
const AMOUNT_KEYS = ['amount', 'montant', 'value', 'valeur', 'cost', 'cout', 'betrag'];

function entry(value: unknown, fallbackName: string | undefined, toneOf: (status: unknown) => CoverageTone): CoverageEntry | null {
  if (typeof value === 'string') {
    return value.trim() ? { name: value.trim(), tone: toneOf(undefined), notes: [], references: [] } : null;
  }
  if (!isRecord(value)) return null;
  const name = text(pick(value, NAME_KEYS)) ?? fallbackName;
  if (!name) return null;
  return {
    name: humanizeCode(name),
    tone: toneOf(pick(value, STATUS_KEYS)),
    reason: text(pick(value, REASON_KEYS)),
    notes: strings(pick(value, NOTE_KEYS)),
    amount: amount(pick(value, AMOUNT_KEYS)),
    references: unique(citationsOf(value).map((item) => item.reference)),
  };
}

function isEntry(value: CoverageEntry | null): value is CoverageEntry {
  return value !== null;
}

/** "Building items" and "Building items (shop window, skylight)" name the same thing. */
function sameItem(a: string, b: string): boolean {
  const [first, second] = [token(a), token(b)];
  return first.length >= 4 && second.length >= 4 && (first.startsWith(second) || second.startsWith(first));
}

const GUARANTEE_KEYS = ['coverage_decisions', 'guarantees', 'garanties', 'garanties_concernees', 'garantie', 'perils', 'coverages', 'couvertures', 'risks', 'risques'];

/** Guarantees as a list or as a map keyed by peril, at the top level or in the status object. */
function guaranteeEntries(coverage: Rec | undefined): CoverageEntry[] {
  if (!coverage) return [];
  for (const container of [coverage, ...Object.values(coverage).filter(isRecord)]) {
    const value = pick(container, GUARANTEE_KEYS);
    let items: CoverageEntry[] = [];
    if (Array.isArray(value)) {
      items = value.map((item) => entry(item, undefined, guaranteeTone)).filter(isEntry);
    } else if (isRecord(value)) {
      items = Object.entries(value)
        .filter(([, item]) => pick(item, STATUS_KEYS) !== undefined)
        .map(([key, item]) => entry(item, key, guaranteeTone))
        .filter(isEntry);
    }
    if (items.length > 0) return items.map((item) => ({ ...item, peril: perilKey(item.name) }));
  }
  return [];
}

const LINE_KEYS = ['conditions', 'items', 'line_items', 'postes', 'lignes', 'positions', 'breakdown', 'ventilation', 'detail_postes', 'damages', 'dommages', 'details'];

/** Claim items with an amount (the settlement's breakdown of the claimed amount). */
function lineEntries(settlement: Rec | undefined): CoverageEntry[] {
  for (const key of LINE_KEYS) {
    const value = pick(settlement, [key]);
    if (!Array.isArray(value)) continue;
    const items = value
      .map((item) => (isRecord(item) ? entry(item, undefined, statusTone) : null))
      .filter((item): item is CoverageEntry => item !== null && item.amount !== undefined);
    if (items.length > 0) return items;
  }
  return [];
}

// ── Rules: deductible, Cat-Nat, IRSI, expert appraisal, recourse ──────────────

const APPLIES_KEYS = ['applies', 'applicable', 'applique', 'required', 'requise', 'requis', 'necessaire', 'needed', 'possible'];
const RULE_REASON_KEYS = ['reason', 'motif', 'explanation', 'commentaire', 'comment', 'justification', 'precision'];
const DEDUCTIBLE_AMOUNT_KEYS = ['franchise_applicable', 'deductible_applicable', 'montant', 'montant_eur', 'montant_chf', 'amount', 'montant_franchise', 'value', 'valeur', 'deductible', 'franchise'];

function rule(value: unknown): CoverageRule | undefined {
  if (typeof value === 'boolean') return { applies: value };
  if (!isRecord(value)) {
    const detail = text(value);
    if (!detail) return undefined;
    const applies = flag(detail);
    return applies === null ? { applies, detail } : { applies };
  }
  return {
    applies: flag(pick(value, APPLIES_KEYS)),
    detail: text(pick(value, ['delai_suggere', 'suggested_delay', 'deadline', 'delai'])),
    reason: text(pick(value, RULE_REASON_KEYS)),
  };
}

function deductibleRule(value: unknown): CoverageRule | undefined {
  const direct = amount(value);
  if (direct !== undefined) return { applies: true, amount: direct };
  if (!isRecord(value)) return undefined;
  const ruleAmount = amount(pick(value, DEDUCTIBLE_AMOUNT_KEYS));
  const applies = pick(value, ['applies', 'applicable', 'applique']);
  return {
    applies: applies === undefined ? (ruleAmount !== undefined ? true : null) : flag(applies),
    amount: ruleAmount,
    detail: text(pick(value, ['deductible_rule', 'regle', 'rule', 'calcul', 'bareme'])),
    reason: text(pick(value, RULE_REASON_KEYS)),
  };
}

function recourseRule(value: unknown, against: string[]): (CoverageRule & { against: string[] }) | undefined {
  if (value === undefined) return against.length > 0 ? { applies: true, against } : undefined;
  if (!isRecord(value)) return { applies: flag(value), against };
  const direct = pick(value, APPLIES_KEYS);
  // Recourse split by route (IRSI, third party): possible when one of them is, and the
  // third-party route explains it best.
  const thirdPartyFirst = (key: string) => Number(/tiers|third|responsab|haftpflicht/.test(token(key)));
  const routes = Object.entries(value)
    .sort(([a], [b]) => thirdPartyFirst(b) - thirdPartyFirst(a))
    .map(([, child]) => child);
  const flags = routes
    .map((child) => (isRecord(child) ? pick(child, APPLIES_KEYS) : child))
    .filter((child): child is boolean => typeof child === 'boolean');
  return {
    applies: direct !== undefined ? flag(direct) : flags.length > 0 ? flags.some(Boolean) : null,
    reason: text(pick(value, RULE_REASON_KEYS)) ?? routes.map((child) => text(pick(child, RULE_REASON_KEYS))).find(Boolean),
    against,
  };
}

// ── Settlement amounts ───────────────────────────────────────────────────────

const AMOUNT_CONTAINERS = ['montants', 'amounts', 'totals', 'totaux', 'calcul', 'calculation', 'decision_recommandee', 'recommended_decision', 'recommendation', 'recommandation'];
const ELIGIBLE_KEYS = ['estimated_repairs', 'estimated_damage', 'eligible_amount', 'covered_amount', 'retained_amount', 'montant_retenu', 'total_retenu', 'montant_estime_reparations', 'montant_estime_des_reparations', 'total_estimated_cost', 'estimated_amount', 'assessed_amount', 'montant_evalue', 'montant_estime'];
const RECOMMENDED_KEYS = ['recommended_indemnity', 'recommended_settlement', 'recommended_amount', 'recommended_payout', 'net_indemnity', 'montant_indemnisation_recommandee', 'montant_indemnisation_recommande', 'montant_recommande', 'indemnite_recommandee', 'indemnisation_recommandee', 'montant_indemnisation', 'indemnite_nette'];
const SETTLEMENT_DEDUCTIBLE_KEYS = ['deductible_applicable', 'franchise_applicable', 'deductible', 'franchise', 'montant_franchise', 'selbstbehalt'];

/** First amount found in the settlement or in its amount sub-objects ("montants"). */
function settlementAmount(settlement: Rec | undefined, read: (source: Rec) => number | undefined): number | undefined {
  if (!settlement) return undefined;
  const containers = [settlement, ...AMOUNT_CONTAINERS.map((key) => record(pick(settlement, [key])))];
  for (const container of containers) {
    const value = container ? read(container) : undefined;
    if (value !== undefined) return value;
  }
  return undefined;
}

const BASIS_KEYS = ['base_de_calcul', 'calculation_basis', 'basis', 'justificatifs', 'pieces_retenues'];

function conditionTexts(settlement: Rec | undefined): { conditions: string[]; basis: string[] } {
  const value = pick(settlement, ['conditions', 'reserves', 'reservations', 'conditions_reglement']);
  if (!isRecord(value)) return { conditions: strings(value), basis: strings(pick(settlement, BASIS_KEYS)) };
  return {
    conditions: Object.entries(value)
      .filter(([key]) => !BASIS_KEYS.includes(token(key)))
      .flatMap(([, child]) => strings(child)),
    basis: strings(pick(value, BASIS_KEYS)),
  };
}

function derivedTone(...groups: CoverageEntry[][]): CoverageTone {
  const tones = new Set(groups.flat().map((item) => item.tone));
  const doubtful = tones.has('excluded') || tones.has('review') || tones.has('partial');
  if (tones.has('covered')) return doubtful ? 'partial' : 'covered';
  if (tones.has('excluded')) return 'excluded';
  return tones.has('review') || tones.has('partial') ? 'review' : 'unknown';
}

const TONE_ORDER: CoverageTone[] = ['covered', 'partial', 'review', 'excluded', 'unknown', 'notConcerned'];

/** Every coverage status, in display order. */
export const COVERAGE_TONES: readonly CoverageTone[] = TONE_ORDER;

/** Entries grouped by status (covered first), keeping the analysis order within a status. */
export function sortByTone(entries: CoverageEntry[]): CoverageEntry[] {
  return entries
    .map((item, index) => ({ item, index }))
    .sort((a, b) => TONE_ORDER.indexOf(a.item.tone) - TONE_ORDER.indexOf(b.item.tone) || a.index - b.index)
    .map(({ item }) => item);
}

export interface AmountSegment {
  /** Part of the claimed amount: covered, to review, excluded, undetermined or not retained. */
  kind: 'covered' | 'review' | 'excluded' | 'unknown' | 'notRetained';
  amount: number;
  /** Share of the claimed amount, in percent. */
  percent: number;
}

/** How the claimed amount splits: by claim item when listed, else retained vs not retained. */
export function amountBreakdown(view: CoverageView, claimed?: number): AmountSegment[] {
  const total = (tones: CoverageTone[]) =>
    view.lines.filter((line) => tones.includes(line.tone)).reduce((sum, line) => sum + (line.amount ?? 0), 0);
  let parts: Array<[AmountSegment['kind'], number]>;
  if (view.lines.length > 0) {
    parts = [
      ['covered', total(['covered'])],
      ['review', total(['partial', 'review'])],
      ['excluded', total(['excluded'])],
      ['unknown', total(['unknown', 'notConcerned'])],
    ];
  } else {
    const { eligible } = view.amounts;
    if (claimed === undefined || eligible === undefined || claimed - eligible < 1) return [];
    parts = [['covered', eligible], ['notRetained', claimed - eligible]];
  }
  const base = Math.max(claimed ?? 0, parts.reduce((sum, [, value]) => sum + value, 0));
  if (base <= 0) return [];
  return parts
    .filter(([, value]) => value > 0)
    .map(([kind, value]) => ({ kind, amount: value, percent: Math.round((value / base) * 100) }));
}

const SUMMARY_KEYS = ['synthese', 'summary', 'resume', 'conclusion', 'commentaire', 'comment', 'explication'];

/** The coverage and settlement analyses among the LLM outputs of a case. */
export function coverageOutputs(llmOutputs: unknown): { coverage?: Rec; settlement?: Rec } {
  const found: { coverage?: Rec; settlement?: Rec } = {};
  if (!isRecord(llmOutputs)) return found;
  for (const [section, subsections] of Object.entries(llmOutputs)) {
    if (!isRecord(subsections)) continue;
    for (const [subsection, output] of Object.entries(subsections)) {
      const parsed = record(record(output)?.parsed);
      if (!parsed || parsed._error) continue;
      const name = token(`${section} ${subsection}`);
      if (!found.coverage && /coverage|couverture|garantie|deckung/.test(name)) found.coverage = parsed;
      else if (!found.settlement && /settlement|payout|reglement|indemni|entschadigung/.test(name)) found.settlement = parsed;
    }
  }
  return found;
}

/** View model of the coverage verdict, amounts, guarantees, exclusions and policy articles. */
export function buildCoverageView(coverage?: Rec, settlement?: Rec): CoverageView {
  const guarantees = guaranteeEntries(coverage);
  const exclusionValue = pick(coverage, ['exclusions_applicable', 'exclusions_applicables', 'applicable_exclusions', 'exclusions', 'exclusions_retenues']);
  const exclusionList = Array.isArray(exclusionValue) ? exclusionValue : pick(exclusionValue, ['items', 'liste', 'list', 'exclusions', 'details']);
  const attentionKeys = ['points_de_vigilance', 'points_of_attention', 'attention_points', 'vigilance', 'reserves', 'reservations', 'warnings', 'alertes'];
  const lines = lineEntries(settlement);
  // An exclusion that matches an excluded claim item is shown once, on the item.
  const exclusions = (Array.isArray(exclusionList) ? exclusionList : [])
    .map((item) => entry(item, undefined, exclusionTone))
    .filter(isEntry)
    .filter((exclusion) => {
      const line = lines.find((item) => item.tone === 'excluded' && sameItem(item.name, exclusion.name));
      if (line) line.references = unique([...line.references, ...exclusion.references]);
      return !line;
    });

  const statusValue = pick(coverage, ['overall_status', 'statut_couverture', 'statut_global', 'coverage_status', 'status', 'statut', 'decision', 'verdict']);
  const statusRecord = record(statusValue);
  const claimLevel = record(pick(coverage, ['claim_level_summary', 'resume_dossier', 'conclusion_globale', 'synthese_dossier']));
  const status = statusRecord ? pick(statusRecord, ['decision', 'status', 'statut', 'verdict']) : statusValue ?? pick(claimLevel, ['status', 'statut']);
  let tone = statusTone(status);
  if (tone === 'unknown' || tone === 'notConcerned') tone = derivedTone(guarantees, exclusions, lines);

  const eventValue = record(pick(coverage, ['event_assessment', 'insured_event', 'evenement', 'event', 'evenement_garanti', 'evenement_assure']));
  const coverageDeductible = deductibleRule(pick(coverage, ['franchise', 'deductible', 'selbstbehalt', 'franchise_applicable']));
  const deductible = settlementAmount(settlement, (source) => deductibleRule(pick(source, SETTLEMENT_DEDUCTIBLE_KEYS))?.amount);
  const eligible = settlementAmount(settlement, (source) => amount(pick(source, ELIGIBLE_KEYS)));
  const recommended = settlementAmount(settlement, (source) => amount(pick(source, RECOMMENDED_KEYS)));
  const recommendation = record(pick(settlement, ['decision_recommandee', 'recommended_decision', 'recommendation', 'recommandation']));
  const against = strings(pickDeep(settlement, ['third_party_recourse_basis', 'recourse_against', 'recourse_basis', 'against', 'contre', 'cible', 'subrogation_target', 'tiers_responsable']));
  const { conditions, basis } = conditionTexts(settlement);

  const articleValue = pick(coverage, ['applicable_articles', 'articles_applicables', 'articles', 'articles_cg', 'policy_articles']);
  const articles = (Array.isArray(articleValue) ? articleValue : []).flatMap((item): CoverageArticle[] => {
    if (typeof item === 'string') return item.trim() ? [{ reference: item.trim(), tone: 'unknown' }] : [];
    const reference = text(pick(item, ['article', 'reference', 'ref', 'titre', 'title', 'name', 'nom']));
    if (!reference) return [];
    const articleStatus = pick(item, ['conclusion', 'status', 'statut', 'applicable', 'applies']);
    return [{
      reference,
      status: text(articleStatus),
      tone: statusTone(articleStatus),
      effect: text(pick(item, ['effet', 'effect', 'motif', 'reason', 'impact', 'explanation', 'explication'])),
    }];
  });

  const summary = text(pick(coverage, SUMMARY_KEYS)) ?? text(pick(statusRecord, SUMMARY_KEYS));
  const attention = unique([...strings(pick(coverage, attentionKeys)), ...strings(pick(exclusionValue, attentionKeys))]);
  const citations = uniqueCitations([...allCitations(coverage), ...allCitations(settlement)]);
  const coverageAmount = coverageDeductible?.amount;

  return {
    tone,
    summary,
    coveredHighlight: text(pick(claimLevel, ['covered_core_peril', 'covered', 'couvert', 'garantie_principale'])),
    notCoveredHighlights: strings(pick(claimLevel, ['main_uncovered_items', 'uncovered_items', 'non_couvert', 'elements_non_couverts'])),
    event: eventValue
      ? {
        cause: text(pick(eventValue, ['cause', 'nature', 'description', 'type', 'category'])),
        covered: flag(pick(eventValue, ['covered_event', 'covered', 'couvert', 'garanti', 'insured', 'assure'])),
      }
      : undefined,
    amounts: { eligible, deductible, recommended },
    settlementNote:
      text(pick(settlement, ['commentaire', 'comment', 'rationale', 'justification', 'summary', 'synthese', 'recommendation', 'recommandation']))
      ?? text(pick(recommendation, ['commentaire', 'comment', 'rationale', 'summary', 'motif'])),
    lines,
    guarantees,
    exclusionsSummary: record(exclusionValue) ? text(pick(exclusionValue, SUMMARY_KEYS)) : undefined,
    exclusions,
    attention,
    conditions,
    basis,
    rules: {
      deductible: coverageDeductible ?? (deductible !== undefined ? { applies: true, amount: deductible } : undefined),
      catNat: rule(pick(coverage, ['cat_nat', 'catnat', 'regime_cat_nat', 'cat_nat_regime'])),
      irsi: rule(pick(coverage, ['irsi', 'convention_irsi'])),
      expertise: rule(pickDeep(settlement, ['complementary_expertise_required', 'expertise_complementaire_necessaire', 'expertise_complementaire', 'expert_appraisal', 'expert_appraisal_required', 'expertise_required', 'expertise_requise', 'expertise'])),
      recourse: recourseRule(pickDeep(settlement, ['third_party_recourse_possible', 'recours_possible', 'recourse_possible', 'recourse', 'recours', 'subrogation']), against),
    },
    deductibleMismatch:
      coverageAmount !== undefined && deductible !== undefined && Math.abs(coverageAmount - deductible) >= 1
        ? { coverage: coverageAmount, settlement: deductible }
        : undefined,
    articles,
    citations,
    hasContent:
      tone !== 'unknown'
      || !!summary
      || guarantees.length + exclusions.length + lines.length + attention.length + articles.length + citations.length > 0
      || eligible !== undefined
      || recommended !== undefined,
  };
}
