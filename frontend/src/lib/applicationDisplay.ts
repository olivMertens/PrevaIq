import type { ApplicationListItem, ApplicationMetadata, ExtractedField } from '@/lib/types';

type DisplayApplication = ApplicationListItem | ApplicationMetadata;
type FieldMap = Record<string, string>;

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

function titleFromFiles(app: DisplayApplication): string | null {
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
  let prefix = 'Sinistre';
  if (persona.includes('automotive') || persona.includes('auto')) prefix = 'Sinistre Auto';
  else if (persona.includes('habitation') || persona.includes('property')) prefix = 'Sinistre Habitation';
  else if (persona.includes('health') || persona.includes('sante')) prefix = 'Sinistre Santé';
  return `${prefix} — ${stem}`;
}

export function getApplicationDisplayTitle(app: DisplayApplication): string {
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
  const fileTitle = titleFromFiles(app);
  if (fileTitle) return fileTitle;
  if (app.external_reference) return app.external_reference;
  return app.id.substring(0, 8).toUpperCase();
}
