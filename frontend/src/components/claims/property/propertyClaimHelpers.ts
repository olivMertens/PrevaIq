// Pure helpers for the property-claims cockpit (moved unchanged from the former overview).
import { textValue } from '@/lib/applicationDisplay';
import { formatAmount, type CurrencyCode } from '@/lib/currency';
import { analysisFieldsMarkdown } from './analysisMarkdown';

// Extract a field value from extracted_fields, searching with multiple key patterns
export function getFieldValue(extractedFields: Record<string, unknown>, keys: string[], defaultValue: string = ''): string {
  for (const key of keys) {
    if (extractedFields[key] && typeof extractedFields[key] === 'object' && 'value' in (extractedFields[key] as Record<string, unknown>)) {
      const val = (extractedFields[key] as { value: unknown }).value;
      const text = textValue(val);
      if (text) return text;
    }
    for (const [fk, fv] of Object.entries(extractedFields)) {
      if (fk.endsWith(`:${key}`) && fv && typeof fv === 'object' && 'value' in (fv as Record<string, unknown>)) {
        const val = (fv as { value: unknown }).value;
        const text = textValue(val);
        if (text) return text;
      }
    }
  }
  return defaultValue;
}

// Fields belonging to dossier info (personal/policy)
export const DOSSIER_FIELDS = new Set([
  'NomAssure', 'AssuréNom', 'AssuréPrenom', 'AdresseAssure',
  'EmailAssure', 'TelephoneAssure', 'NumeroContrat', 'NumeroPolice',
  'NumeroSocietaire', 'FormuleContrat', 'NomSouscripteur',
  'DateNaissance', 'Profession', 'NumeroSecuriteSociale',
  'FormuleDemandee', 'CotisationMensuelle',
]);

// Parsing of the full AI analysis into topic tabs lives in a pure, tested module.
export { parseAiSummary, TAB_KEYWORDS, type SyntheseTabKey } from './analysisMarkdown';

// Fields belonging to damage info
export const DOMMAGES_FIELDS = new Set([
  'DateSinistre', 'NatureSinistre', 'LieuSinistre', 'DescriptionSinistre',
  'MontantEstime', 'DateConstat', 'ExpertNom', 'ExpertContact',
  'MesuresConservatoires', 'NombreItemsEndommages', 'FranchiseApplicable',
  'TiersImplique', 'NiveauUrgence', 'StatutTabac', 'NiveauRisque',
  'OverallDamageSeverity', 'DamageAreas', 'ConstatAmiable', 'Vehicule',
]);

// Get translated label for a field name (t = useTranslations('claims') from caller)
export type TranslateFn = (key: string, values?: any) => string;

export function getFieldLabel(fieldName: string, t?: TranslateFn): string {
  if (t) {
    try { return t(`fields.${fieldName}`); } catch { /* fall through */ }
  }
  return fieldName;
}

// Detect file type from filename
export function getFileTypeInfo(filename: string, t: TranslateFn): { label: string; icon: 'pdf' | 'image' | 'video' | 'document' } {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 'heic'];
  const videoExts = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'm4v'];
  if (ext === 'pdf') return { label: 'PDF', icon: 'pdf' };
  if (imageExts.includes(ext)) return { label: t('classifyDoc.imageTitle'), icon: 'image' };
  if (videoExts.includes(ext)) return { label: t('classifyDoc.videoTitle'), icon: 'video' };
  return { label: ext.toUpperCase() || t('classifyDoc.attachmentTitle'), icon: 'document' };
}

// Classify document type based on filename (i18n-compatible)
export function classifyDocument(filename: string, t: TranslateFn): { type: string; summary: string } {
  const lower = filename.toLowerCase();
  if (lower.includes('declaration') || lower.includes('sinistre')) {
    return { type: t('classifyDoc.coverageTitle'), summary: t('classifyDoc.coverageDesc') };
  }
  if (lower.includes('photo') || lower.includes('degat') || lower.includes('dégât') || lower.includes('damage')) {
    return { type: t('classifyDoc.damageTitle'), summary: t('classifyDoc.damageDesc') };
  }
  if (lower.includes('facture') || lower.includes('invoice') || lower.includes('devis')) {
    return { type: t('classifyDoc.repairTitle'), summary: t('classifyDoc.repairDesc') };
  }
  if (lower.includes('meteo') || lower.includes('météo') || lower.includes('weather')) {
    return { type: t('classifyDoc.stormTitle'), summary: t('classifyDoc.stormDesc') };
  }
  if (lower.includes('souscription') || lower.includes('sante') || lower.includes('santé') || lower.includes('health')) {
    return { type: t('classifyDoc.underwritingTitle'), summary: t('classifyDoc.underwritingDesc') };
  }
  if (lower.includes('questionnaire') || lower.includes('medical')) {
    return { type: t('classifyDoc.medicalTitle'), summary: t('classifyDoc.medicalDesc') };
  }
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'];
  if (imageExts.includes(ext)) {
    return { type: t('classifyDoc.damageTitle'), summary: t('classifyDoc.imageDesc') };
  }
  if (ext === 'pdf') {
    return { type: t('classifyDoc.attachmentTitle'), summary: t('classifyDoc.pdfDesc') };
  }
  return { type: t('classifyDoc.attachmentTitle'), summary: t('classifyDoc.attachmentDesc') };
}

// Format parsed JSON into Markdown for the AI summary display (lines of the Markdown text).
// NOTE: Do NOT use t() for dynamic field names — next-intl throws MISSING_MESSAGE
// errors that crash React. Use a static lookup map + auto-formatting fallback instead.
export function formatParsedFields(
  parsed: Record<string, unknown>,
  t?: TranslateFn,
  locale = 'en',
  currency: CurrencyCode = 'EUR',
): string[] {
  // Comprehensive static label map — covers all known LLM output field names
  const labelMap: Record<string, string> = {
    reference_dossier: 'fileReference', refDossier: 'fileReference',
    montant_estime_reparations: 'estimatedRepairs', montantEstime: 'estimatedAmount',
    franchise_applicable: 'deductible', franchiseApplicable: 'deductible', franchise: 'deductible',
    montant_indemnisation_recommande: 'recommendedPayout', indemnisationRecommandee: 'recommendedPayout',
    couverture_applicable: 'applicableCoverage', couvertureApplicable: 'applicableCoverage',
    garantie: 'coverage', exclusions: 'exclusions', responsabilite: 'liability',
    observations: 'observations', recommandation: 'recommendation', recommendation: 'recommendation',
    conclusion: 'conclusion', risque: 'risk', score: 'score',
    analyse_reglement: 'settlementAnalysis', analyseReglement: 'settlementAnalysis',
    details_calcul: 'calculationDetails', detailsCalcul: 'calculationDetails',
    total_dommages: 'totalDamage', totalDommages: 'totalDamage',
    plafond_garantie: 'coverageLimit', plafondGarantie: 'coverageLimit',
    vetuste: 'depreciation', taux_vetuste: 'depreciationRate', tauxVetuste: 'depreciationRate',
    contrat: 'contract', conditions: 'conditions', formule: 'contractPlan',
    numero: 'number', numeroContrat: 'contractNumber', typeContrat: 'contractType',
    'plafond biens mobiliers': 'contentsLimit', 'plafond biens immobiliers': 'buildingLimit',
    'plafond objets de valeur': 'valuablesLimit', summary: 'summary', synthese: 'summary',
    description: 'description', cause: 'cause', date: 'date', lieu: 'location',
    montant: 'amount', status: 'status', coverage_status: 'coverageStatus',
    fraud_indicators: 'fraudIndicators', risk_level: 'riskLevel', severity: 'severity',
  };
  const markdown = analysisFieldsMarkdown(parsed, {
    // Static label map only: next-intl throws on missing dynamic keys.
    label: (key) => (labelMap[key] && t ? t(`parsedFields.${labelMap[key]}`) : null),
    money: (amount) => formatAmount(amount, currency, locale),
    yes: t?.('parsedFields.yes') || 'Yes',
    no: t?.('parsedFields.no') || 'No',
  });
  return markdown ? markdown.split('\n') : [];
}

/** Parse an amount such as "6560 EUR", "10 825 €", "CHF 1'697'400.00" or "6,560.00" (NaN if absent). */
export function parseAmount(raw: string): number {
  const cleaned = String(raw || '').replace(/[^\d.,]/g, '');
  if (!cleaned) return NaN;
  const lastSeparator = Math.max(cleaned.lastIndexOf(','), cleaned.lastIndexOf('.'));
  const decimals = lastSeparator >= 0 ? cleaned.length - lastSeparator - 1 : 0;
  if (lastSeparator >= 0 && decimals > 0 && decimals <= 2) {
    const integer = cleaned.slice(0, lastSeparator).replace(/[.,]/g, '');
    return Number(`${integer}.${cleaned.slice(lastSeparator + 1)}`);
  }
  return Number(cleaned.replace(/[.,]/g, ''));
}
