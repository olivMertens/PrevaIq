import type { ApplicationListItem, ApplicationMetadata, ExtractedField } from '@/lib/types';

type DisplayApplication = ApplicationListItem | ApplicationMetadata;
type FieldMap = Record<string, string>;
type DisplayLocale = 'en' | 'fr' | 'de';

const HTML_TAG_RE = /<[^>]+>/g;
const HTML_ONLY_RE = /^(?:<\/?(?:td|tr|th|table|tbody|thead|p|span|div|br)\s*\/?>\s*)+$/i;

export function textValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed || HTML_ONLY_RE.test(trimmed)) return null;
    const stripped = trimmed.replace(HTML_TAG_RE, '').trim();
    return stripped || null;
  }
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    const parts = value.map(textValue).filter(Boolean);
    return parts.length ? parts.join(', ') : null;
  }
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    for (const key of ['name', 'full_name', 'label', 'value', 'description']) {
      const nested = textValue(obj[key]);
      if (nested) return nested;
    }
  }
  return null;
}

function extractedFieldsToMap(fields?: Record<string, ExtractedField>): FieldMap {
  const mapped: FieldMap = {};
  if (!fields) return mapped;
  for (const [key, field] of Object.entries(fields)) {
    const normalizedKey = key.split(':').pop() || key;
    const value = textValue(field?.value);
    if (value) mapped[normalizedKey] = value;
  }
  return mapped;
}

function getField(fields: FieldMap, keys: string[]): string | null {
  for (const key of keys) {
    const value = fields[key];
    if (value) return value;
  }
  return null;
}

function shortSubject(subject: string): string {
  return subject.split('—')[0].split('–')[0].trim();
}

function titleFromFiles(app: DisplayApplication, locale: DisplayLocale): string | null {
  if (!('files' in app) || !Array.isArray(app.files)) return null;
  const candidate = app.files
    .map((file) => file.filename)
    .find((filename) =>
      /dommage|crash|accident|choc|enfonc|fissur|rayur|cass|bris|porti[eè]re|pare.?chocs|aile|capot|coffre|phare|vitr/i.test(filename)
    );
  if (!candidate) return null;
  const stem = candidate
    .replace(/\.[^.]+$/, '')
    .replace(/^(crash|accident|sinistre|photo|image)[_-]/i, '')
    .replace(/[_-]+/g, ' ')
    .trim();
  if (!stem) return null;
  // Prefix by persona so a habitation file is not mislabelled "Sinistre Auto".
  const persona = ('persona' in app && app.persona ? String(app.persona) : '').toLowerCase();
  const prefixes = {
    en: { claim: 'Claim', automotive: 'Auto Claim', property: 'Property Claim', health: 'Health Claim' },
    fr: { claim: 'Sinistre', automotive: 'Sinistre Auto', property: 'Sinistre Habitation', health: 'Sinistre Santé' },
    de: { claim: 'Schadenfall', automotive: 'Kfz-Schaden', property: 'Sachschaden', health: 'Gesundheitsschaden' },
  }[locale];
  let prefix = prefixes.claim;
  if (persona.includes('automotive') || persona.includes('auto')) prefix = prefixes.automotive;
  else if (persona.includes('habitation') || persona.includes('property')) prefix = prefixes.property;
  else if (persona.includes('health') || persona.includes('sante')) prefix = prefixes.health;
  return `${prefix} — ${stem}`;
}

export function getApplicationDisplayTitle(
  app: DisplayApplication,
  requestedLocale: string = 'en'
): string {
  const locale: DisplayLocale =
    requestedLocale === 'fr' || requestedLocale === 'de' ? requestedLocale : 'en';
  if ('summary_title' in app && app.summary_title) return app.summary_title;

  const fields: FieldMap = {
    ...('key_fields' in app ? app.key_fields : undefined),
    ...('extracted_fields' in app ? extractedFieldsToMap(app.extracted_fields) : undefined),
  };

  const name = getField(fields, [
    'NomAssure', 'AssuréNom', 'AssureNom', 'InsuredName', 'Assure', 'Assuré',
    'NomClient', 'ClientName', 'PolicyholderName', 'NomSouscripteur',
    'ApplicantName', 'PatientName', 'Claimant', 'ClaimantName', 'NomReclamant',
    'Conducteur', 'DriverName', 'NomConducteur', 'Borrower', 'BorrowerName',
    'BorrowerFullName', 'Emprunteur',
  ]);
  const vehicle = [
    getField(fields, ['VehicleMake', 'MarqueVehicule', 'Marque']),
    getField(fields, ['VehicleModel', 'ModeleVehicule', 'Modèle']),
  ].filter(Boolean).join(' ').trim();
  const subject = getField(fields, [
    'NatureSinistre', 'CauseOfLoss', 'ClaimType', 'LossType', 'TypeSinistre',
    'IncidentDescription', 'DescriptionSinistre', 'FormuleDemandee', 'PolicyProduct',
    'CoverageType', 'OverallDamageSeverity', 'EstimatedDamageCategory',
    'PolicyNumber', 'NumeroPolice', 'ClaimNumber', 'NumeroSinistre', 'LicensePlate',
    'Immatriculation',
  ]) || vehicle;

  if (name && subject) return `${name} — ${shortSubject(subject)}`;
  if (name) return name;
  if (vehicle) return vehicle;
  if (subject) return shortSubject(subject);
  const fileTitle = titleFromFiles(app, locale);
  if (fileTitle) return fileTitle;
  if (app.external_reference) return app.external_reference;
  return app.id.substring(0, 8).toUpperCase();
}

export interface CompactTitle {
  /** Insured person or company, shortened. */
  holder: string;
  /** First clause of the claim subject, if the title has one. */
  subject: string | null;
  /** Holder and subject on one line. */
  text: string;
}

// Beyond these lengths a person's given names become initials and parts are clipped.
const PERSON_NAME_MAX = 20;
const HOLDER_MAX = 32;
const SUBJECT_MAX = 28;
const UPPER = 'A-ZÀ-ÖØ-Þ';
const LOWER = 'a-zß-öø-ÿ';
const GIVEN_NAME_RE = new RegExp(`^[${UPPER}][${LOWER}]+(?:-[${UPPER}][${LOWER}]+)*$`);
const SURNAME_RE = new RegExp(`^[${UPPER}]+(?:[-'’][${UPPER}]+)*$`);
const COMPANY_FORM_RE = /\s+(?:GmbH|AG|SA|SAS|SASU|SARL|Sàrl|EURL|SNC|SCI|Ltd|LLC|Inc|SE|KG)\.?$/;
const CLAUSE_BREAK_RE = /\s[-–—]\s|\s?\(|[,;:]\s/;

function clip(text: string, max: number): string {
  if (text.length <= max) return text;
  const cut = text.slice(0, max - 1);
  const space = cut.lastIndexOf(' ');
  return `${(space >= max / 2 ? cut.slice(0, space) : cut).replace(/[\s,;:/·—–-]+$/, '')}…`;
}

function isSurname(word: string): boolean {
  return word.length >= 2 && SURNAME_RE.test(word);
}

/** "Olivier MERTENS LAFFITE" -> "O. MERTENS LAFFITE"; other shapes are left untouched. */
function abbreviateGivenNames(name: string): string {
  const words = name.split(/\s+/);
  const given = words.map((word) => GIVEN_NAME_RE.test(word));
  if (!words.some(isSurname) || words.some((word, i) => !given[i] && !isSurname(word))) return name;
  const first = given.indexOf(true);
  const last = given.lastIndexOf(true);
  // One block of given names before or after the surname ("Prénom NOM" or "NOM Prénom").
  const singleBlock = first >= 0 && given.slice(first, last + 1).every(Boolean);
  if (!singleBlock || (first !== 0 && last !== words.length - 1)) return name;
  return words
    .map((word, i) => (given[i] ? word.split('-').map((part) => `${part[0]}.`).join('-') : word))
    .join(' ');
}

function compactHolder(holder: string): string {
  const base = holder.replace(/\s*\([^)]*\)/g, '').trim() || holder.trim();
  const isCompany = COMPANY_FORM_RE.test(base);
  const name = base.replace(COMPANY_FORM_RE, '').trim() || base;
  return clip(!isCompany && name.length > PERSON_NAME_MAX ? abbreviateGivenNames(name) : name, HOLDER_MAX);
}

/** Short form of a case title for headers, menus and lists (the full title stays on hover). */
export function compactApplicationTitle(title: string): CompactTitle {
  const [head, ...rest] = title.split(' — ');
  const holder = compactHolder(head);
  const tail = rest.join(' — ').trim();
  const subject = tail ? clip(tail.split(CLAUSE_BREAK_RE)[0].trim() || tail, SUBJECT_MAX) : null;
  return { holder, subject, text: subject ? `${holder} · ${subject}` : holder };
}
