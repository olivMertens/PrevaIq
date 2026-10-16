'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  Scale,
  Activity,
  TrendingUp,
  AlertTriangle,
  ListChecks,
  Flag,
  FileText,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  Image,
  Film,
  ZoomIn,
  FileDown,
  Layers,
  X,
  Loader2,
  RefreshCw,
  Maximize2,
  Upload,
} from 'lucide-react';
import type { ApplicationMetadata, ContextLabel, ContextTask } from '@/lib/types';
import type { FieldSchema } from '@/lib/types';
import { getMediaUrl, getAnalyzerSchema, runUnderwritingAnalysis, getApplication, addFilesToApplication, runSentimentAnalysis } from '@/lib/api';
import type { FraudAnalysisResponse } from '@/lib/api';
import { brand, isWorkbenchSystem } from '@/lib/brand';
import clsx from 'clsx';
import { useTranslations, useLocale } from 'next-intl';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import GalleryLightbox from '../GalleryLightbox';
import type { GalleryItem } from '../GalleryLightbox';
import { generateNoteDeReglement } from './generateNoteDeReglement';
import UnderwritingDecisionFooter from '@/components/UnderwritingDecisionFooter';
import FraudAnalysisPanel from './FraudAnalysisPanel';
import CustomerAffiliationBanner from './CustomerAffiliationBanner';
import NextBestActionPanel from './NextBestActionPanel';
import CommunicationGenerator from './CommunicationGenerator';
import CommunicationClientPanel from './CommunicationClientPanel';
import { severityFromSentiment } from './sentimentTone';
import ClientSentimentPanel from './ClientSentimentPanel';
import ChronologicalOverview from '../ChronologicalOverview';
import { textValue } from '@/lib/applicationDisplay';

interface PropertyCasualtyClaimsOverviewProps {
  application: ApplicationMetadata | null;
  onApplicationUpdate?: (app: ApplicationMetadata) => void;
}

// Extract a field value from extracted_fields, searching with multiple key patterns
function getFieldValue(extractedFields: Record<string, unknown>, keys: string[], defaultValue: string = ''): string {
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

// French label mapping for CamelCase field names from Azure Content Understanding
const FIELD_LABELS: Record<string, string> = {
  NomAssure: 'Nom de l\'assuré',
  AssuréNom: 'Nom de l\'assuré',
  AssuréPrenom: 'Prénom de l\'assuré',
  AdresseAssure: 'Adresse de l\'assuré',
  EmailAssure: 'Email de l\'assuré',
  TelephoneAssure: 'Téléphone de l\'assuré',
  NumeroContrat: 'N° de contrat',
  NumeroPolice: 'N° de police',
  NumeroSocietaire: 'N° de sociétaire',
  FormuleContrat: 'Formule du contrat',
  DateSinistre: 'Date du sinistre',
  NatureSinistre: 'Nature du sinistre',
  LieuSinistre: 'Lieu du sinistre',
  DescriptionSinistre: 'Description du sinistre',
  MontantEstime: 'Montant estimé',
  DateConstat: 'Date du constat',
  ExpertNom: 'Nom de l\'expert',
  ExpertContact: 'Contact de l\'expert',
  MesuresConservatoires: 'Mesures conservatoires',
  NombreItemsEndommages: 'Nb biens endommagés',
  FranchiseApplicable: 'Franchise applicable',
  TiersImplique: 'Tiers impliqué',
  NiveauUrgence: 'Niveau d\'urgence',
  NomSouscripteur: 'Nom du souscripteur',
  DateNaissance: 'Date de naissance',
  Profession: 'Profession',
  NumeroSecuriteSociale: 'N° de sécurité sociale',
  FormuleDemandee: 'Formule demandée',
  CotisationMensuelle: 'Cotisation mensuelle',
  StatutTabac: 'Statut tabagique',
  NiveauRisque: 'Niveau de risque',
  OverallDamageSeverity: 'Sévérité globale des dommages',
  DamageAreas: 'Zones endommagées',
  ConstatAmiable: 'Constat amiable',
  Vehicule: 'Véhicule',
};

// Fields belonging to dossier info (personal/policy)
const DOSSIER_FIELDS = new Set([
  'NomAssure', 'AssuréNom', 'AssuréPrenom', 'AdresseAssure',
  'EmailAssure', 'TelephoneAssure', 'NumeroContrat', 'NumeroPolice',
  'NumeroSocietaire', 'FormuleContrat', 'NomSouscripteur',
  'DateNaissance', 'Profession', 'NumeroSecuriteSociale',
  'FormuleDemandee', 'CotisationMensuelle',
]);

// Parse the free-form AI summary text into named sections keyed by tab.
// Sections are detected by lines ending with ":" (e.g. "Décision : approved" or "Dommages :").
// Each section header is matched against keyword lists to route it to the correct tab.
type SyntheseTabKey = 'overview' | 'damages' | 'decision' | 'risk' | 'timeline';

// Custom markdown components for the Synthèse IA dialog — renders LLM output
// with bold/italic/headings/lists. Note: react-markdown follows CommonMark,
// so `__text__` and `**text**` both produce <strong>, and `*text*`/`_text_`
// produce <em>. True underline is not part of CommonMark — we render <u>
// tags via the `u` component (LLM must emit raw <u>...</u> for underline,
// which is preserved as text and rendered through the override below).
const SYNTHESE_MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <div className="text-indigo-700 font-semibold text-base mt-3 mb-1">{children}</div>,
  h2: ({ children }) => <div className="text-indigo-700 font-semibold mt-3 mb-1">{children}</div>,
  h3: ({ children }) => <div className="text-indigo-600 font-semibold mt-2 mb-1">{children}</div>,
  h4: ({ children }) => <div className="text-slate-700 font-semibold mt-2 mb-1">{children}</div>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  em: ({ children }) => <em className="italic text-slate-800">{children}</em>,
  ul: ({ children }) => <ul className="list-disc list-inside space-y-1 my-1 text-slate-700">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 my-1 text-slate-700">{children}</ol>,
  li: ({ children }) => <li className="text-slate-700">{children}</li>,
  p: ({ children }) => <p className="my-1 text-slate-700 leading-relaxed">{children}</p>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-600 underline hover:text-indigo-800">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="font-mono text-xs bg-slate-100 text-slate-800 px-1 py-0.5 rounded">{children}</code>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-indigo-300 pl-3 italic text-slate-600 my-2">{children}</blockquote>
  ),
};

const TAB_KEYWORDS: Record<SyntheseTabKey, string[]> = {
  overview: ['vue', 'synthèse', 'synthese', 'résumé', 'resume', 'overview', 'contexte', 'dossier', 'assuré', 'assure', 'sinistre'],
  damages: ['dommage', 'préjudice', 'prejudice', 'bien', 'mobilier', 'immobilier', 'damage'],
  decision: ['décision', 'decision', 'couverture', 'recommandation', 'indemnisation', 'franchise', 'garantie', 'coverage', 'verdict'],
  risk: ['risque', 'risk', 'fraude', 'fraud', 'alerte', 'alert', 'indicateur', 'signal', 'anomalie'],
  timeline: ['chronologie', 'timeline', 'historique', 'date', 'événement', 'evenement'],
};

function parseAiSummary(text: string): Record<SyntheseTabKey, string> {
  const out: Record<SyntheseTabKey, string[]> = {
    overview: [], damages: [], decision: [], risk: [], timeline: [],
  };
  if (!text) return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, v.join('\n').trim()])) as Record<SyntheseTabKey, string>;

  // First pass: detect section headers and bucket lines
  const lines = text.split('\n');
  let currentTab: SyntheseTabKey = 'overview';
  for (const line of lines) {
    const trimmed = line.trim();
    // Section header detection: short line ending with ":"
    if (trimmed.length > 0 && trimmed.length < 60 && (trimmed.endsWith(':') || trimmed.endsWith(' :'))) {
      const header = trimmed.replace(/[:\s]+$/, '').toLowerCase();
      // Find best matching tab
      let matched: SyntheseTabKey | null = null;
      for (const [tab, keywords] of Object.entries(TAB_KEYWORDS) as [SyntheseTabKey, string[]][]) {
        if (keywords.some(kw => header.includes(kw))) { matched = tab; break; }
      }
      if (matched) {
        currentTab = matched;
        out[currentTab].push(line); // keep the header itself in the section
        continue;
      }
    }
    out[currentTab].push(line);
  }

  return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, v.join('\n').trim()])) as Record<SyntheseTabKey, string>;
}

// Fields belonging to damage info
const DOMMAGES_FIELDS = new Set([
  'DateSinistre', 'NatureSinistre', 'LieuSinistre', 'DescriptionSinistre',
  'MontantEstime', 'DateConstat', 'ExpertNom', 'ExpertContact',
  'MesuresConservatoires', 'NombreItemsEndommages', 'FranchiseApplicable',
  'TiersImplique', 'NiveauUrgence', 'StatutTabac', 'NiveauRisque',
  'OverallDamageSeverity', 'DamageAreas', 'ConstatAmiable', 'Vehicule',
]);

// Get translated label for a field name (t = useTranslations('claims') from caller)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type TranslateFn = (key: string, values?: any) => string;

function getFieldLabel(fieldName: string, t?: TranslateFn): string {
  if (t) {
    try { return t(`fields.${fieldName}`); } catch { /* fall through */ }
  }
  return FIELD_LABELS[fieldName] || fieldName;
}

// Detect file type from filename
function getFileTypeInfo(filename: string, t?: TranslateFn): { label: string; icon: 'pdf' | 'image' | 'video' | 'document' } {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 'heic'];
  const videoExts = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'm4v'];
  if (ext === 'pdf') return { label: 'PDF', icon: 'pdf' };
  if (imageExts.includes(ext)) return { label: 'Image', icon: 'image' };
  if (videoExts.includes(ext)) return { label: t?.('classifyDoc.videoTitle') || 'Vidéo', icon: 'video' };
  return { label: ext.toUpperCase() || 'Document', icon: 'document' };
}

// Classify document type based on filename (i18n-compatible)
function classifyDocument(filename: string, t?: TranslateFn): { type: string; summary: string } {
  const lower = filename.toLowerCase();
  if (lower.includes('declaration') || lower.includes('sinistre')) {
    return { type: t?.('classifyDoc.coverageTitle') || 'Couverture', summary: t?.('classifyDoc.coverageDesc') || 'Déclaration de sinistre — document de couverture et circonstances' };
  }
  if (lower.includes('photo') || lower.includes('degat') || lower.includes('dégât') || lower.includes('damage')) {
    return { type: t?.('classifyDoc.damageTitle') || 'Dommages', summary: t?.('classifyDoc.damageDesc') || 'Preuves photographiques des dommages constatés' };
  }
  if (lower.includes('facture') || lower.includes('invoice') || lower.includes('devis')) {
    return { type: t?.('classifyDoc.repairTitle') || 'Réparation', summary: t?.('classifyDoc.repairDesc') || 'Facture ou devis de réparation' };
  }
  if (lower.includes('meteo') || lower.includes('météo') || lower.includes('weather')) {
    return { type: t?.('classifyDoc.stormTitle') || 'Tempête', summary: t?.('classifyDoc.stormDesc') || "Données météorologiques confirmant l'événement climatique" };
  }
  if (lower.includes('souscription') || lower.includes('sante') || lower.includes('santé') || lower.includes('health')) {
    return { type: t?.('classifyDoc.underwritingTitle') || 'Souscription', summary: t?.('classifyDoc.underwritingDesc') || 'Dossier de souscription santé — données médicales et risques' };
  }
  if (lower.includes('questionnaire') || lower.includes('medical')) {
    return { type: t?.('classifyDoc.medicalTitle') || 'Médical', summary: t?.('classifyDoc.medicalDesc') || 'Questionnaire médical — antécédents et déclarations' };
  }
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'];
  if (imageExts.includes(ext)) {
    return { type: t?.('classifyDoc.damageTitle') || 'Dommages', summary: t?.('classifyDoc.imageDesc') || 'Image jointe au dossier — preuve visuelle' };
  }
  if (ext === 'pdf') {
    return { type: 'Document', summary: t?.('classifyDoc.pdfDesc') || 'Document PDF joint au dossier' };
  }
  return { type: t?.('classifyDoc.attachmentTitle') || 'Pièce jointe', summary: t?.('classifyDoc.attachmentDesc') || 'Document ajouté au dossier' };
}

// Header Strip driven by extracted fields + backend context_labels
function HeaderStrip({ application, fraudResult }: { application: ApplicationMetadata | null; fraudResult: FraudAnalysisResponse | null }) {
  const t = useTranslations('claims');
  const ef = application?.extracted_fields || {};
  const lineOfBusiness = getFieldValue(ef, ['LineOfBusiness', 'NatureContrat', 'BrancheAssurance'], t('header.defaultBranch'));
  const causeOfLoss = getFieldValue(ef, ['CauseOfLoss', 'NatureSinistre', 'CauseDuSinistre'], t('header.defaultCause'));
  const insuredName = getFieldValue(ef, ['InsuredName', 'NomAssure', 'NomSouscripteur'], '');
  const paidIndemnity = getFieldValue(ef, ['PaidIndemnity', 'IndemniteVersee'], '—');
  const paidExpense = getFieldValue(ef, ['PaidExpense', 'FraisExpert'], '—');
  const totalIncurred = getFieldValue(ef, ['TotalIncurred', 'MontantEstime', 'MontantTotal'], '—');
  const currentReserve = getFieldValue(ef, ['CurrentReserve', 'ReserveActuelle'], '—');

  // Backend-driven context labels (flat array)
  const contextLabels: ContextLabel[] = application?.context_labels || [];

  // Map urgency to Tailwind bg color
  const urgencyBg: Record<string, string> = {
    info: 'bg-blue-500', success: 'bg-emerald-600',
    warning: 'bg-amber-600', critical: 'bg-rose-700',
  };
  // Map label color field to Tailwind bg class
  const colorBg = (lbl: ContextLabel) => {
    const c = lbl.color;
    const map: Record<string, string> = {
      blue: 'bg-blue-500', emerald: 'bg-emerald-600', sky: 'bg-sky-600',
      purple: 'bg-purple-600', orange: 'bg-orange-600', cyan: 'bg-cyan-600',
      indigo: 'bg-indigo-600', amber: 'bg-amber-600', rose: 'bg-rose-700',
      slate: 'bg-slate-500',
    };
    return map[c] || urgencyBg[lbl.urgency] || 'bg-slate-500';
  };

  // Sinistre majeur threshold
  const estimatedAmount = parseFloat(
    (totalIncurred || '0').replace(/[^\d.,]/g, '').replace(',', '.') || '0'
  );
  const isMajor = estimatedAmount > 5000;

  return (
    <div className="bg-gradient-to-r from-indigo-600 to-indigo-700 text-white px-5 py-2.5 flex-shrink-0">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-6 text-sm">
          <div><span className="text-indigo-200 text-xs">{t('header.branch')}</span> <span className="font-medium">{lineOfBusiness}</span></div>
          <div><span className="text-indigo-200 text-xs">{t('header.cause')}</span> <span className="font-medium">{causeOfLoss}</span></div>
          {insuredName && (
            <div>
              <span className="text-indigo-200 text-xs">{t('header.insured')}</span>{' '}
              {application?.external_reference ? (
                <a href={`/customers/${application.external_reference}`} className="font-medium underline decoration-indigo-300 hover:decoration-white cursor-pointer">{insuredName}</a>
              ) : (
                <span className="font-medium">{insuredName}</span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-5">
          <div className="text-center"><div className="text-xs text-indigo-200">{t('header.indemnified')}</div><div className="font-semibold">{paidIndemnity}</div></div>
          <div className="text-center"><div className="text-xs text-indigo-200">{t('header.expertFees')}</div><div className="font-semibold">{paidExpense}</div></div>
          <div className="text-center"><div className="text-xs text-indigo-200">{t('header.totalEstimated')}</div><div className="font-semibold text-amber-300">{totalIncurred}</div></div>
          <div className="text-center"><div className="text-xs text-indigo-200">{t('header.reserve')}</div><div className="font-semibold">{currentReserve}</div></div>
          {isMajor && <span className="px-2.5 py-1 bg-amber-600 rounded-full text-xs font-medium">{t('badges.sinistreMajeur')}</span>}
        </div>
      </div>
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {/* Backend-driven context labels */}
        {contextLabels.map((lbl) => (
          <div key={lbl.key} className="relative group/label">
            <span className={clsx('px-2 py-0.5 text-white text-xs rounded flex items-center gap-1 cursor-default', colorBg(lbl))}>
              {(lbl.type === 'guarantee' || lbl.icon === 'flag') && <Flag className="w-3 h-3" />}
              {String(lbl.label)}
            </span>
            {lbl.tooltip && (
              <div className="absolute left-0 top-full mt-1 z-50 w-72 bg-white text-slate-800 rounded-lg shadow-xl border border-slate-200 p-3 opacity-0 invisible group-hover/label:opacity-100 group-hover/label:visible transition-all duration-200 pointer-events-none group-hover/label:pointer-events-auto">
                <p className="text-[11px] text-slate-600 leading-relaxed">{typeof lbl.tooltip === 'string' ? lbl.tooltip : Array.isArray(lbl.tooltip) ? (lbl.tooltip as any[]).map((f: any) => typeof f === 'string' ? f : (f.summary || f.title || f.category || '')).filter(Boolean).join(' — ').slice(0, 300) : JSON.stringify(lbl.tooltip)}</p>
                {lbl.source_url && (() => {
                  try {
                    const u = new URL(lbl.source_url);
                    return (
                      <a href={lbl.source_url} target="_blank" rel="noopener noreferrer"
                         className="inline-flex items-center gap-1 text-[11px] text-indigo-600 hover:text-indigo-800 hover:underline mt-1">
                        <ExternalLink className="w-3 h-3 flex-shrink-0" />{u.hostname}
                      </a>
                    );
                  } catch { return null; }
                })()}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// Format parsed JSON into human-readable labels for AI summary display
// NOTE: Do NOT use t() for dynamic field names — next-intl throws MISSING_MESSAGE
// errors that crash React. Use a static lookup map + auto-formatting fallback instead.
function formatParsedFields(parsed: Record<string, unknown>, prefix = '', t?: TranslateFn): string[] {
  const lines: string[] = [];
  // Comprehensive static label map — covers all known LLM output field names
  const labelMap: Record<string, string> = {
    reference_dossier: 'Réf. dossier',
    refDossier: 'Réf. dossier',
    montant_estime_reparations: 'Montant estimé réparations',
    montantEstime: 'Montant estimé',
    franchise_applicable: 'Franchise applicable',
    franchiseApplicable: 'Franchise applicable',
    franchise: 'Franchise',
    montant_indemnisation_recommande: 'Indemnisation recommandée',
    indemnisationRecommandee: 'Indemnisation recommandée',
    couverture_applicable: 'Couverture applicable',
    couvertureApplicable: 'Couverture applicable',
    garantie: 'Garantie',
    exclusions: 'Exclusions',
    responsabilite: 'Responsabilité',
    observations: 'Observations',
    recommandation: 'Recommandation',
    conclusion: 'Conclusion',
    risque: 'Risque',
    score: 'Score',
    analyse_reglement: 'Analyse règlement',
    analyseReglement: 'Analyse règlement',
    details_calcul: 'Détails du calcul',
    detailsCalcul: 'Détails du calcul',
    total_dommages: 'Total dommages',
    totalDommages: 'Total dommages',
    plafond_garantie: 'Plafond de garantie',
    plafondGarantie: 'Plafond de garantie',
    vetuste: 'Vétusté',
    taux_vetuste: 'Taux de vétusté',
    tauxVetuste: 'Taux de vétusté',
    contrat: 'Contrat',
    conditions: 'Conditions',
    formule: 'Formule du contrat',
    numero: 'Numéro',
    numeroContrat: 'N° de contrat',
    typeContrat: 'Type de contrat',
    'plafond biens mobiliers': 'Plafond biens mobiliers',
    'plafond biens immobiliers': 'Plafond biens immobiliers',
    'plafond objets de valeur': 'Plafond objets de valeur',
    summary: 'Résumé',
    synthese: 'Synthèse',
    description: 'Description',
    cause: 'Cause',
    date: 'Date',
    lieu: 'Lieu',
    montant: 'Montant',
    status: 'Statut',
    coverage_status: 'Statut de couverture',
    fraud_indicators: 'Indicateurs de fraude',
    risk_level: 'Niveau de risque',
    severity: 'Gravité',
    recommendation: 'Recommandation',
  };
  for (const [key, value] of Object.entries(parsed)) {
    if (key.startsWith('_')) continue;
    // Use static label map — never call t() with dynamic keys
    const label = labelMap[key] || key.replace(/_/g, ' ').replace(/\b[a-z]/g, c => c.toUpperCase());
    if (typeof value === 'string' && value.trim()) {
      lines.push(`${prefix}${label} : ${value}`);
    } else if (typeof value === 'number') {
      const formatted = key.toLowerCase().includes('montant') || key.toLowerCase().includes('franchise') || key.toLowerCase().includes('indemnisation') || key.toLowerCase().includes('total') || key.toLowerCase().includes('plafond')
        ? `${value.toLocaleString('fr-FR')} €`
        : String(value);
      lines.push(`${prefix}${label} : ${formatted}`);
    } else if (typeof value === 'boolean') {
      lines.push(`${prefix}${label} : ${value ? 'Oui' : 'Non'}`);
    } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      lines.push(`${prefix}${label} :`);
      lines.push(...formatParsedFields(value as Record<string, unknown>, prefix + '  ', t));
    } else if (Array.isArray(value) && value.length > 0) {
      lines.push(`${prefix}${label} :`);
      for (const item of value) {
        if (typeof item === 'object' && item !== null) {
          lines.push(...formatParsedFields(item as Record<string, unknown>, prefix + '  - ', t));
        } else {
          lines.push(`${prefix}  - ${String(item)}`);
        }
      }
    }
  }
  return lines;
}

// Main Component
export default function PropertyCasualtyClaimsOverview({ application, onApplicationUpdate }: PropertyCasualtyClaimsOverviewProps) {
  const t = useTranslations('claims');
  const tReport = useTranslations('claims.report.note');
  const locale = useLocale();
  const [checkedTasks, setCheckedTasks] = useState<number[]>([]);
  const [expandedSection, setExpandedSection] = useState<string>('liability');
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [showSchema, setShowSchema] = useState(false);
  const [detailDialog, setDetailDialog] = useState<string | null>(null);
  const [syntheseTab, setSyntheseTab] = useState<'overview' | 'damages' | 'decision' | 'risk' | 'timeline' | 'raw'>('overview');
  const [analyzerSchema, setAnalyzerSchema] = useState<FieldSchema | null>(null);
  const [aiDialogOpen, setAiDialogOpen] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [fraudResult, setFraudResult] = useState<FraudAnalysisResponse | null>(null);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const aiDialogRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  const handleFraudComplete = useCallback((result: FraudAnalysisResponse) => {
    setFraudResult(result);
    // Refresh application to get updated context_labels with fraud data
    if (application?.id && onApplicationUpdate) {
      getApplication(application.id).then(onApplicationUpdate).catch(() => {});
    }
  }, [application?.id, onApplicationUpdate]);

  const handleAddFiles = useCallback(async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0 || !application) return;
    setUploadingFiles(true);
    setProgressMessage(t('progress.extracting', { total: fileList.length }));
    try {
      await addFilesToApplication(application.id, Array.from(fileList), true);
      // Use SSE for real-time progress instead of polling (fixes flicker)
      const apiBase = typeof window !== 'undefined' && (window as unknown as Record<string, string>).__NEXT_PUBLIC_API_URL
        ? (window as unknown as Record<string, string>).__NEXT_PUBLIC_API_URL
        : (process.env.NEXT_PUBLIC_API_URL || '');
      const sseUrl = `${apiBase}/api/applications/${application.id}/progress`;
      if (sseRef.current) { sseRef.current.close(); }
      const es = new EventSource(sseUrl);
      sseRef.current = es;
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.message) setProgressMessage(data.message);
          if (data.status === 'completed' || data.status === 'done' || data.status === 'error') {
            es.close();
            sseRef.current = null;
            setUploadingFiles(false);
            setProgressMessage(null);
            // Fetch final state once and update parent
            getApplication(application.id).then((updated) => {
              onApplicationUpdate?.(updated);
            }).catch(() => {});
          }
        } catch { /* ignore parse errors */ }
      };
      es.onerror = () => {
        // SSE failed — fall back to single poll
        es.close();
        sseRef.current = null;
        setTimeout(async () => {
          try {
            const updated = await getApplication(application.id);
            onApplicationUpdate?.(updated);
          } catch { /* ignore */ }
          setUploadingFiles(false);
          setProgressMessage(null);
        }, 5000);
      };
      // Safety timeout
      setTimeout(() => { es.close(); sseRef.current = null; setUploadingFiles(false); setProgressMessage(null); }, 180000);
    } catch (e) {
      console.error('File upload failed:', e);
      setUploadingFiles(false);
      setProgressMessage(null);
    }
  }, [application, onApplicationUpdate, t]);

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => { sseRef.current?.close(); };
  }, []);

  const ef = application?.extracted_fields || {};
  const llmOutputs = (application?.llm_outputs || {}) as Record<string, unknown>;
  const files = application?.files || [];
  const docMarkdown = String((application as unknown as Record<string, unknown>)?.document_markdown || '');

  // Customer 360 cross-reference — by external_reference or auto-match by name
  const [customerData, setCustomerData] = useState<Record<string, unknown> | null>(null);
  const [matchedCustomerId, setMatchedCustomerId] = useState<string | null>(null);
  useEffect(() => {
    const extRef = application?.external_reference;
    if (extRef) {
      setMatchedCustomerId(extRef);
      fetch(`/api/customers/${encodeURIComponent(extRef)}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data) setCustomerData(data); })
        .catch(() => {});
      return;
    }
    // Auto-match by insured name from extracted fields
    const insuredName = getFieldValue(ef, ['NomAssure', 'AssuréNom', 'NomSouscripteur'], '');
    if (!insuredName) return;
    fetch('/api/customers')
      .then(r => r.ok ? r.json() : [])
      .then((customers: Array<{ id: string; name: string }>) => {
        const nameParts = insuredName.toLowerCase().split(/\s+/);
        const match = customers.find((c: { id: string; name: string }) => {
          const cName = c.name?.toLowerCase() || '';
          return nameParts.some(p => p.length > 2 && cName.includes(p));
        });
        if (match) {
          setMatchedCustomerId(match.id);
          fetch(`/api/customers/${encodeURIComponent(match.id)}`)
            .then(r => r.ok ? r.json() : null)
            .then(data => { if (data) setCustomerData(data); })
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, [application?.external_reference, ef]);

  // Fetch analyzer schema on demand
  useEffect(() => {
    if (!showSchema || analyzerSchema) return;
    const persona = application?.persona || 'habitation_claims';
    getAnalyzerSchema(persona)
      .then(schema => setAnalyzerSchema(schema))
      .catch(() => {});
  }, [showSchema, analyzerSchema, application?.persona]);

  // Close AI dialog on Escape
  useEffect(() => {
    if (!aiDialogOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setAiDialogOpen(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [aiDialogOpen]);

  // Auto-trigger Sentiment Agent when analysis is complete but sentiment not yet computed
  useEffect(() => {
    if (!application?.id || aiAnalyzing) return;
    const hasSentiment = !!(application as any)?.sentiment_analysis;
    const hasAnalysis = !!application?.llm_outputs && Object.keys(application.llm_outputs).length > 0;
    if (hasAnalysis && !hasSentiment) {
      runSentimentAnalysis(application.id)
        .then((sa) => {
          if (sa && onApplicationUpdate) {
            // Refresh application to get updated sentiment_analysis
            getApplication(application.id).then(onApplicationUpdate).catch(() => {});
          }
        })
        .catch(() => {});
    }
  }, [application?.id, application?.llm_outputs, (application as any)?.sentiment_analysis, aiAnalyzing, onApplicationUpdate]);

  const handleAiDialogBackdropClick = (e: React.MouseEvent) => {
    if (aiDialogRef.current && !aiDialogRef.current.contains(e.target as Node)) {
      setAiDialogOpen(false);
    }
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  // Resume polling if application is already analyzing (e.g., page refresh)
  useEffect(() => {
    if (application?.processing_status === 'analyzing' && !pollingRef.current && !aiAnalyzing) {
      setAiAnalyzing(true);
      pollingRef.current = setInterval(async () => {
        try {
          const app = await getApplication(application.id);
          if (app.processing_status !== 'analyzing') {
            if (pollingRef.current) clearInterval(pollingRef.current);
            pollingRef.current = null;
            if ((app as any).processing_error) {
              setAiError((app as any).processing_error);
            } else if (onApplicationUpdate) {
              onApplicationUpdate(app);
            }
            setAiAnalyzing(false);
          }
        } catch {
          // Ignore transient polling errors
        }
      }, 3000);
    }
  }, [application?.processing_status, application?.id, aiAnalyzing, onApplicationUpdate]);

  const handleLaunchAnalysis = useCallback(async () => {
    if (!application) return;
    setAiLoading(true);
    setAiError(null);
    try {
      // Start analysis in background mode — returns immediately
      await runUnderwritingAnalysis(application.id, undefined, true, locale);
      setAiDialogOpen(false);
      setAiLoading(false);
      setAiAnalyzing(true);

      // Poll for completion every 3 seconds
      if (pollingRef.current) clearInterval(pollingRef.current);
      pollingRef.current = setInterval(async () => {
        try {
          const app = await getApplication(application.id);
          if (app.processing_status !== 'analyzing') {
            // Analysis finished — update app state before clearing analyzing flag
            if (pollingRef.current) clearInterval(pollingRef.current);
            pollingRef.current = null;
            if ((app as any).processing_error) {
              setAiError((app as any).processing_error);
            } else if (onApplicationUpdate) {
              onApplicationUpdate(app);
            }
            setAiAnalyzing(false);
          }
        } catch {
          // Ignore transient polling errors
        }
      }, 3000);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : 'Analyse IA échouée');
      setAiLoading(false);
    }
  }, [application, onApplicationUpdate]);

  // Derive key info from document_markdown when structured fields are missing or unusable.
  const markdownDerivedFields = useMemo(() => {
    if (!docMarkdown) return [];
    const fields: { name: string; value: string }[] = [];
    const seen = new Set<string>();

    // Strip HTML tags/entities and collapse whitespace so a value never renders as "</td>".
    const clean = (raw: string): string =>
      raw
        .replace(/<[^>]*>/g, ' ')
        .replace(/&nbsp;|&amp;|&lt;|&gt;|&#\d+;/gi, ' ')
        .replace(/\s+/g, ' ')
        .trim();

    // Map a source label (document wording, FR) to a canonical field key localised via getFieldLabel.
    const canonicalFor = (label: string): string | null => {
      const l = label.toLowerCase();
      if (/(n°|numero|numéro).*(contrat|police)/.test(l)) return 'NumeroContrat';
      if (/(n°|numero|numéro).*(client|sociétaire|societaire|adhérent|adherent)/.test(l)) return 'NumeroSocietaire';
      if (/(nom|prénom|prenom|assuré|assure|souscripteur|conducteur)/.test(l)) return 'NomAssure';
      if (/adresse/.test(l)) return 'AdresseAssure';
      if (/e-?mail|courriel/.test(l)) return 'EmailAssure';
      if (/t[ée]l[ée]?phone|\btél\b|\btel\b/.test(l)) return 'TelephoneAssure';
      if (/date.*(sinistre|incident)/.test(l)) return 'DateSinistre';
      if (/(nature|cause).*(sinistre|dommage)/.test(l)) return 'NatureSinistre';
      if (/franchise/.test(l)) return 'FranchiseApplicable';
      if (/(montant|total|estimation|estim[ée])/.test(l)) return 'MontantEstime';
      return null;
    };

    const pushField = (canonical: string, rawValue: string) => {
      const value = clean(rawValue);
      if (!value || value.length < 2 || /[<>]/.test(value)) return; // empty / fragment / residual markup
      if (seen.has(canonical)) return;
      seen.add(canonical);
      fields.push({ name: getFieldLabel(canonical, t), value: value.slice(0, 120) });
    };

    // 1) Preferred: parse HTML tables from Content Understanding (prebuilt-layout) output.
    //    Rows are <tr><td>N° de contrat :</td><td>HAB-33-…</td></tr> — label and value sit
    //    in separate cells, which the previous single-line regex could not read (it captured "</td>").
    const rowRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
    let rowMatch: RegExpExecArray | null;
    while ((rowMatch = rowRe.exec(docMarkdown)) !== null) {
      const cells = Array.from(rowMatch[1].matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi)).map((m) => m[1]);
      if (cells.length < 2) continue;
      const canonical = canonicalFor(clean(cells[0]));
      if (canonical) pushField(canonical, cells[1]);
    }

    // 2) Fallback: plain-text "Label : value" lines (non-HTML markdown). Capture stops at
    //    the first "<" so a leaked tag can never become the value.
    if (fields.length === 0) {
      const patterns: [RegExp, string][] = [
        [/(?:numéro|n°)\s*(?:de\s*)?(?:contrat|police)\s*[:：]\s*([^\n<]+)/i, 'NumeroContrat'],
        [/(?:nom|assuré|souscripteur)\s*[:：]\s*([^\n<]+)/i, 'NomAssure'],
        [/adresse\s*[:：]\s*([^\n<]+)/i, 'AdresseAssure'],
        [/(?:date)\s*(?:du\s*)?(?:sinistre|incident)\s*[:：]\s*([^\n<]+)/i, 'DateSinistre'],
        [/(?:nature|cause)\s*(?:du\s*)?(?:sinistre|dommage)\s*[:：]\s*([^\n<]+)/i, 'NatureSinistre'],
        [/(?:montant|total|estimation)\s*[:：]\s*([^\n<]+)/i, 'MontantEstime'],
        [/franchise\s*[:：]\s*([^\n<]+)/i, 'FranchiseApplicable'],
      ];
      for (const [regex, canonical] of patterns) {
        const m = docMarkdown.match(regex);
        if (m) pushField(canonical, m[1]);
      }
    }

    // 3) Enrich with Customer 360 profile when available.
    if (customerData) {
      const profile = (customerData as Record<string, unknown>).profile as Record<string, unknown> | undefined;
      if (profile?.name) pushField('NomAssure', String(profile.name));
      if (profile?.email) pushField('EmailAssure', String(profile.email));
      if (profile?.phone) pushField('TelephoneAssure', String(profile.phone));
    }

    return fields;
  }, [docMarkdown, customerData, t]);

  // Derive damages from document_markdown or LLM outputs
  const markdownDerivedDamages = useMemo(() => {
    const items: { description: string; related: string }[] = [];
    const seen = new Set<string>();

    // Normalize a candidate damage phrase; return null when it is junk/a fragment.
    const sanitize = (raw: string): string | null => {
      const s = raw
        .replace(/<[^>]*>/g, ' ') // strip any leaked HTML tags (e.g. </td>)
        .replace(/[*_`#>]+/g, ' ') // strip markdown emphasis / heading / quote marks
        .replace(/&nbsp;|&amp;|&lt;|&gt;/gi, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      if (s.length < 12) return null; // too short → fragment
      if (!/^[A-Za-zÀ-ÖØ-öø-ÿ0-9]/.test(s)) return null; // must start with a letter/digit (rejects "s, …", ", …")
      if (/[<>]/.test(s)) return null; // residual HTML → reject
      return s.slice(0, 180);
    };

    const add = (raw: string) => {
      if (items.length >= 6) return;
      const c = sanitize(raw);
      if (!c) return;
      const key = c.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      items.push({ description: c, related: 'Oui' });
    };

    // 1) Preferred: structured LLM damage_assessment.damage_areas (clean path)
    const damageSection = llmOutputs.damage_assessment as Record<string, unknown> | undefined;
    if (damageSection) {
      for (const [, val] of Object.entries(damageSection)) {
        const sub = val as { parsed?: { damage_areas?: Array<{ location?: string; severity?: string; description?: string }> } } | undefined;
        const areas = sub?.parsed?.damage_areas;
        if (Array.isArray(areas)) {
          for (const area of areas) {
            const head = [area.location, area.description].filter(Boolean).join(' — ');
            const sev = area.severity ? ` (${area.severity})` : '';
            add(`${head}${sev}`);
          }
        }
      }
    }

    // 2) Fallback: derive from document markdown only when no structured areas exist.
    if (items.length === 0 && docMarkdown) {
      const text = docMarkdown.replace(/<[^>]*>/g, ' '); // strip HTML before scanning
      // 2a) Explicit "Dégâts/Dommages constatés : …" labels (value to end of line only)
      const labelPatterns = [
        /(?:dégâts?\s*(?:des\s*eaux?|constatés?))\s*[:：]\s*([^\n\r]+)/gi,
        /(?:dommages?\s*(?:constatés?|visibles?|apparents?))\s*[:：]\s*([^\n\r]+)/gi,
      ];
      for (const re of labelPatterns) {
        let m: RegExpExecArray | null;
        while ((m = re.exec(text)) !== null && items.length < 6) add(m[1]);
      }
      // 2b) Structured photo-analysis bullets: "- **<label>** : <value>" — take the
      // full value of damage-relevant labels instead of matching keyword stems mid-word.
      if (items.length === 0) {
        const bulletRe = /^[\s>*-]*\*\*([^*]+?)\*\*\s*[:：]\s*([^\n\r]+)$/gim;
        let b: RegExpExecArray | null;
        while ((b = bulletRe.exec(docMarkdown)) !== null && items.length < 6) {
          if (/(nature du sinistre|étendue des dommages|éléments?\s+affect|zone affect|dégât|dommage)/i.test(b[1])) {
            add(b[2]);
          }
        }
      }
    }
    return items;
  }, [llmOutputs, docMarkdown]);

  // Build AI summary from LLM outputs
  const aiSummary = useMemo(() => {
    const parts: string[] = [];
    for (const [, subsections] of Object.entries(llmOutputs)) {
      if (subsections && typeof subsections === 'object') {
        for (const [, val] of Object.entries(subsections as Record<string, unknown>)) {
          const sub = val as { parsed?: Record<string, unknown>; raw?: string } | undefined;
          if (sub?.parsed) {
            // Check for summary field first
            if (typeof sub.parsed.summary === 'string' && sub.parsed.summary) {
              parts.push(sub.parsed.summary);
            }
            // Fallback: check for _error (analysis ran but parsing failed)
            else if (typeof sub.parsed._error === 'string') {
              // Skip error entries — don't add them to summary
            }
            // Fallback: format parsed JSON into readable text
            else {
              const lines = formatParsedFields(sub.parsed, '', t);
              if (lines.length > 0) {
                parts.push(lines.join('\n'));
              }
            }
          }
        }
      }
    }
    // If llm_outputs has content but no extractable summaries, show generic
    if (parts.length === 0 && Object.keys(llmOutputs).length > 0) {
      const sectionCount = Object.keys(llmOutputs).length;
      parts.push(t('analysisDialog.analysisComplete', { count: sectionCount }));
    }
    return parts.join('\n\n');
  }, [llmOutputs]);

  // Extract alert signals from LLM outputs, extracted fields, and fraud analysis
  const alertSignals = useMemo(() => {
    const signals: { label: string; level: 'high' | 'medium' | 'low'; detail: string; sourceUrl?: string; sourceTitle?: string }[] = [];

    // --- Fraud-derived signals (prepended) ---
    // SIU referral
    if (fraudResult?.overall_assessment?.siu_referral_recommended) {
      signals.push({
        label: 'Renvoi SIU recommandé',
        level: 'high',
        detail: String(fraudResult.overall_assessment.siu_referral_reason || 'Investigation spéciale recommandée par l\'analyse de fraude'),
      });
    }
    // Fraud attention items
    if (fraudResult?.overall_assessment?.attention_items) {
      for (const item of fraudResult.overall_assessment.attention_items) {
        const level = item.priority === 'high' ? 'high' : item.priority === 'medium' ? 'medium' : 'low';
        signals.push({ label: String(item.label), level: level as 'high' | 'medium' | 'low', detail: String(item.detail) });
      }
    }
    
    // Check estimated amount for high value
    const montant = getFieldValue(ef, ['MontantEstime', 'TotalIncurred', 'MontantTotal'], '');
    const montantNum = parseFloat(String(montant).replace(/[^\d.,]/g, '').replace(',', '.'));
    if (montantNum > 5000) {
      signals.push({ label: 'Montant élevé', level: 'high', detail: `Montant estimé: ${montantNum.toLocaleString('fr-FR')} € — expertise obligatoire au-delà de 5 000 €` });
    }
    
    // Check nature of claim for severity — enriched with web intelligence
    const nature = getFieldValue(ef, ['NatureSinistre', 'CauseOfLoss'], '').toLowerCase();
    if (nature.includes('tempête') || nature.includes('catastrophe') || nature.includes('inondation')) {
      const wi = fraudResult?.web_intelligence;
      const verified = wi && !wi.error ? wi.event_verified : undefined;
      let detail = `Sinistre lié à un événement climatique — vérifier arrêté Cat-Nat`;
      let sourceUrl: string | undefined;
      let sourceTitle: string | undefined;
      if (verified === true) {
        detail = `Événement climatique confirmé par sources publiques`;
        // Find Cat-Nat source URL
        if (wi?.findings) {
          for (const f of wi.findings) {
            if (typeof f !== 'string') {
              const text = `${f.title || ''} ${f.category || ''} ${f.summary || ''}`.toLowerCase();
              if (text.includes('cat-nat') || text.includes('arrêté') || text.includes('catastrophe naturelle')) {
                sourceUrl = String(f.source_url || f.source || '');
                sourceTitle = String(f.title || f.type || f.category || '');
                break;
              }
            }
          }
        }
      } else if (verified === false) {
        detail = `Événement climatique non confirmé par sources publiques — vérification manuelle nécessaire`;
      }
      signals.push({ label: 'Événement climatique', level: verified === false ? 'high' : 'medium', detail, sourceUrl, sourceTitle });
    }
    if (nature.includes('incendie')) {
      signals.push({ label: 'Incendie', level: 'high', detail: 'Sinistre incendie — expertise systématique requise' });
    }
    
    // Check for third party involvement
    const tiers = getFieldValue(ef, ['TiersImplique'], '').toLowerCase();
    if (tiers === 'oui') {
      signals.push({ label: 'Tiers impliqué', level: 'medium', detail: 'Un tiers est impliqué — vérifier convention IRSI et recours possible' });
    }
    
    // Check urgency level
    const urgence = getFieldValue(ef, ['NiveauUrgence'], '').toLowerCase();
    if (urgence === 'critique' || urgence === 'eleve') {
      signals.push({ label: 'Urgence élevée', level: 'high', detail: `Niveau d'urgence: ${urgence} — traitement prioritaire requis` });
    }
    
    // Check for preexisting damage from image analysis
    const preexisting = getFieldValue(ef, ['PreexistingDamage'], '').toLowerCase();
    if (preexisting === 'probable' || preexisting === 'certain') {
      signals.push({ label: 'Dommages préexistants', level: 'high', detail: 'Dommages préexistants détectés sur les photos — vérifier antériorité' });
    }
    
    // Check description for fraud keywords
    const desc = getFieldValue(ef, ['DescriptionSinistre'], '').toLowerCase();
    if (desc.includes('incohéren') || desc.includes('contradictoi')) {
      signals.push({ label: 'Incohérence détectée', level: 'high', detail: 'Incohérence dans la description du sinistre — investigation recommandée' });
    }
    
    // Parse LLM outputs for additional signals
    for (const [sectionName, subsections] of Object.entries(llmOutputs)) {
      if (!subsections || typeof subsections !== 'object') continue;
      for (const [, val] of Object.entries(subsections as Record<string, unknown>)) {
        const sub = val as { parsed?: Record<string, unknown>; raw?: string } | undefined;
        const parsed = sub?.parsed;
        if (parsed?.fraud_indicators && Array.isArray(parsed.fraud_indicators) && parsed.fraud_indicators.length > 0) {
          signals.push({ label: 'Indicateurs de fraude', level: 'high', detail: String(parsed.fraud_indicators[0]) });
        }
        if (parsed?.exclusions && typeof parsed.exclusions === 'string' && parsed.exclusions.length > 0 && !parsed.exclusions.toLowerCase().includes('aucune')) {
          signals.push({ label: 'Exclusions possibles', level: 'medium', detail: String(parsed.exclusions).slice(0, 120) });
        }
        // Coverage verification signals
        if (sectionName === 'liability_assessment' && parsed?.coverage_status) {
          const status = String(parsed.coverage_status).toLowerCase();
          if (status.includes('non') || status.includes('exclu') || status.includes('refus')) {
            signals.push({ label: 'Couverture non confirmée', level: 'high', detail: `Statut: ${String(parsed.coverage_status)}` });
          }
        }
      }
    }

    // ── Missing documents detection ──
    // Check uploaded files against expected documents for this claim type
    const fileNames = files.map(f => f.filename.toLowerCase());
    const hasPhoto = fileNames.some(f => /\.(png|jpg|jpeg|gif|webp|bmp)$/i.test(f));
    const hasDeclaration = fileNames.some(f => f.includes('declaration') || f.includes('déclaration') || f.includes('sinistre'));
    const hasDevis = fileNames.some(f => f.includes('devis') || f.includes('estimate'));
    const hasFacture = fileNames.some(f => f.includes('facture') || f.includes('invoice'));
    const hasConstat = fileNames.some(f => f.includes('constat') || f.includes('amiable'));

    const missingDocs: string[] = [];
    if (!hasDeclaration && files.length > 0) missingDocs.push('Déclaration de sinistre');
    if (!hasPhoto) missingDocs.push('Photos des dommages (min. 3)');
    if (!hasDevis && !hasFacture) missingDocs.push('Devis ou facture de réparation');
    // If third party is involved, constat amiable is required
    const tiersVal = getFieldValue(ef, ['TiersImplique'], '').toLowerCase();
    if ((tiersVal === 'oui' || tiersVal.includes('oui')) && !hasConstat) {
      missingDocs.push('Constat amiable (tiers impliqué)');
    }

    if (missingDocs.length > 0) {
      signals.push({
        label: `📎 ${missingDocs.length} pièce${missingDocs.length > 1 ? 's' : ''} manquante${missingDocs.length > 1 ? 's' : ''}`,
        level: 'medium',
        detail: missingDocs.join(' · '),
      });
    }
    
    return signals;
  }, [ef, llmOutputs, fraudResult, files]);

  // Amount comparison: customer claimed vs AI-assessed
  const amountComparison = useMemo(() => {
    // Customer's declared/claimed amount from extracted fields
    const claimedStr = getFieldValue(ef, ['MontantEstime', 'MontantTotal', 'TotalIncurred'], '');
    const claimed = parseFloat(String(claimedStr).replace(/[^\d.,]/g, '').replace(',', '.'));

    // AI-recommended indemnity from LLM payout_calculation
    let recommended = NaN;
    const payoutSection = llmOutputs.payout_calculation as Record<string, unknown> | undefined;
    if (payoutSection) {
      for (const val of Object.values(payoutSection)) {
        const sub = val as { parsed?: Record<string, unknown> } | undefined;
        const p = sub?.parsed;
        if (p) {
          const r = Number(p.montant_indemnisation_recommande || p.montant_indemnisation || p.recommended_payout || 0);
          if (r > 0) { recommended = r; break; }
          const rep = Number(p.montant_estime_reparations || p.total_estimated_cost || 0);
          if (rep > 0 && isNaN(recommended)) { recommended = rep; }
        }
      }
    }

    if (isNaN(claimed) || claimed === 0) return null;
    if (isNaN(recommended) || recommended === 0) return null;

    const delta = claimed - recommended;
    const pctDelta = ((delta / recommended) * 100);
    return { claimed, recommended, delta, pctDelta, hasOverclaim: delta > 0 && pctDelta > 5 };
  }, [ef, llmOutputs]);

  // Build evidence items from actual uploaded files + policy reference PDFs
  const evidenceItems = useMemo(() => {
    const items = files.map(f => {
      const classification = classifyDocument(f.filename, t);
      const fileType = getFileTypeInfo(f.filename, t);
      return {
        source: f.filename,
        type: classification.type,
        summary: classification.summary,
        supports: true,
        challenges: false,
        fileType,
        isPolicyRef: false,
      };
    });
    // Add policy PDFs as reference docs
    items.push({
      source: t('evidence.cgHabitation'),
      type: 'Police',
      summary: t('evidence.cgHabitationDesc'),
      supports: true,
      challenges: false,
      fileType: { label: 'PDF', icon: 'pdf' as const },
      isPolicyRef: true,
    });
    items.push({
      source: t('evidence.cgSante'),
      type: 'Police',
      summary: t('evidence.cgSanteDesc'),
      supports: true,
      challenges: false,
      fileType: { label: 'PDF', icon: 'pdf' as const },
      isPolicyRef: true,
    });
    return items;
  }, [files, t]);

  // Build coherent narrative timeline from extracted fields (correlates with ChronologicalOverview)
  const liabilityEvents = useMemo(() => {
    if (files.length === 0) return [{ date: '—', type: 'Attente', desc: 'En attente de traitement des documents', impact: 'neutral' }];

    const createdDate = application?.created_at ? new Date(application.created_at) : new Date();
    const fmtDate = (d: Date) => `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth() + 1).toString().padStart(2, '0')}`;

    // Try to build from extracted fields first
    const dateSinistre = getFieldValue(ef, ['DateSinistre']);
    const natureSinistre = getFieldValue(ef, ['NatureSinistre']);
    const description = getFieldValue(ef, ['DescriptionSinistre']);
    const lieu = getFieldValue(ef, ['LieuSinistre']);
    const montant = getFieldValue(ef, ['MontantEstime']);
    const mesures = getFieldValue(ef, ['MesuresConservatoires']);
    const nomAssure = getFieldValue(ef, ['NomAssure', 'AssuréNom']);
    const contrat = getFieldValue(ef, ['NumeroContrat']);

    // Parse incident date
    let incidentDate: Date | null = null;
    if (dateSinistre) {
      const parts = dateSinistre.match(/(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})/);
      if (parts) incidentDate = new Date(Number(parts[3].length === 2 ? '20' + parts[3] : parts[3]), Number(parts[2]) - 1, Number(parts[1]));
    }

    // If we have extracted fields, build narrative events
    if (incidentDate && natureSinistre) {
      const events: { date: string; type: string; desc: string; impact: string; sort: number }[] = [];
      const dayAfter = new Date(incidentDate.getTime() + 86400000);
      const twoDaysAfter = new Date(incidentDate.getTime() + 2 * 86400000);

      events.push({ date: fmtDate(incidentDate), type: t('timeline.incident', { nature: natureSinistre }), desc: lieu ? t('timeline.incidentLocation', { location: lieu }) : t('timeline.incidentNoLocation'), impact: 'disputes', sort: incidentDate.getTime() });

      if (description) {
        events.push({ date: fmtDate(dayAfter), type: t('timeline.damage'), desc: nomAssure ? t('timeline.damageDesc', { name: nomAssure }) : t('timeline.damageDescDefault'), impact: 'neutral', sort: dayAfter.getTime() });
      }

      if (mesures) {
        events.push({ date: fmtDate(dayAfter), type: t('timeline.conservatory'), desc: t('timeline.conservatoryDesc'), impact: 'supports', sort: dayAfter.getTime() + 1 });
      }

      events.push({ date: fmtDate(twoDaysAfter), type: t('timeline.declaration'), desc: contrat ? t('timeline.declarationDesc', { contract: contrat }) : t('timeline.declarationDescNoContract'), impact: 'supports', sort: twoDaysAfter.getTime() });

      if (montant) {
        const formatted = !isNaN(Number(montant)) ? Number(montant).toLocaleString(locale === 'en' ? 'en-US' : 'fr-FR') + ' €' : montant;
        events.push({ date: fmtDate(twoDaysAfter), type: t('timeline.estimation', { amount: formatted }), desc: t('timeline.estimationDesc'), impact: 'neutral', sort: twoDaysAfter.getTime() + 1 });
      }

      events.push({ date: fmtDate(createdDate), type: t('timeline.reception'), desc: t('timeline.receptionDesc'), impact: 'supports', sort: createdDate.getTime() });

      events.push({ date: fmtDate(new Date()), type: t('timeline.analysisComplete'), desc: t('timeline.analysisCompleteDesc', { count: files.length }), impact: 'supports', sort: Date.now() });

      // Merge persisted action_history (actions + decisions)
      if (application?.action_history) {
        for (const action of application.action_history) {
          const actionDate = new Date(action.at);

          // Decision entries — rich rendering with icon and justification
          if ((action as Record<string, unknown>).decision) {
            const dec = action as Record<string, unknown>;
            const decisionIcons: Record<string, string> = {
              approve: '✅', approve_with_conditions: '⚠️', defer: '⏳', decline: '❌',
            };
            const icon = decisionIcons[String(dec.decision)] || '📋';
            let desc = dec.notes ? String(dec.notes) : action.source || brand.name;
            if (dec.ai_recommendation) {
              desc += ` — IA: ${dec.ai_recommendation}`;
            }
            if (dec.validation_divergence && dec.validation_divergence !== 'aligned') {
              desc += ' ⚡ Divergence IA/Humain';
            }
            if (dec.conditions) {
              desc += ` | Conditions: ${dec.conditions}`;
            }
            events.push({
              date: fmtDate(actionDate),
              type: `${icon} ${action.label}`,
              desc,
              impact: dec.decision === 'decline' ? 'disputes' : 'supports',
              sort: actionDate.getTime(),
            });
            continue;
          }

          // Generic action_history entries
          const systems = (action.systems || []).filter((s: string) => s && !isWorkbenchSystem(s));
          const uniqueSystems = [...new Set(systems)];
          const badges = uniqueSystems.map((s: string) => {
            if (s === 'SIU') return '🔍 SIU';
            if (s === 'GED') return '📂 GED';
            if (s === 'Email') return '✉️ Email';
            return s;
          }).join(' · ');
          events.push({
            date: fmtDate(actionDate),
            type: action.label,
            desc: badges ? `Systèmes : ${badges}` : action.source,
            impact: action.performed === 'HITL' ? 'disputes' : 'supports',
            sort: actionDate.getTime(),
          });
        }
      }

      // Fallback: synthesize timeline entry from llm_outputs.decision for existing dossiers
      // that have a decision but no action_history entry for it
      const decisionData = (llmOutputs as Record<string, unknown>).decision as Record<string, unknown> | undefined;
      const hasDecisionInHistory = application?.action_history?.some(
        (a: Record<string, unknown>) => !!(a as Record<string, unknown>).decision
      );
      if (decisionData && !hasDecisionInHistory) {
        const decIcons: Record<string, string> = {
          approve: '✅', approve_with_conditions: '⚠️', defer: '⏳', decline: '❌',
        };
        const decLabels: Record<string, string> = {
          approve: 'Décision : Approuvé',
          approve_with_conditions: 'Décision : Approuvé sous conditions',
          defer: 'Décision : Différé',
          decline: 'Décision : Refusé',
        };
        const decStr = String(decisionData.decision || '');
        const icon = decIcons[decStr] || '📋';
        const label = decLabels[decStr] || `Décision : ${decStr}`;
        const decidedAt = decisionData.decided_at
          ? new Date(typeof decisionData.decided_at === 'number' ? decisionData.decided_at * 1000 : String(decisionData.decided_at))
          : new Date();
        events.push({
          date: fmtDate(decidedAt),
          type: `${icon} ${label}`,
          desc: decisionData.notes ? String(decisionData.notes) : 'Décision enregistrée',
          impact: decStr === 'decline' ? 'disputes' : 'supports',
          sort: decidedAt.getTime(),
        });
      }

      events.sort((a, b) => a.sort - b.sort);
      return events;
    }

    // Fallback: simple file-based timeline
    return files.map(f => {
      const classification = classifyDocument(f.filename, t);
      return { date: fmtDate(createdDate), type: classification.type, desc: f.filename, impact: 'supports' };
    });
  }, [files, application, ef, llmOutputs]);

  // Build damage items from extracted fields — only damage-related fields with French labels
  const injuries = useMemo(() => {
    const items: { diagnosis: string; related: string }[] = [];
    for (const [key, val] of Object.entries(ef)) {
      const fieldVal = val as { field_name?: string; value?: unknown } | undefined;
      if (!fieldVal || fieldVal.value == null || fieldVal.value === '') continue;
      const rawName = fieldVal.field_name || key.split(':').pop() || key;
      // Only include damage-related fields
      if (!DOMMAGES_FIELDS.has(rawName)) continue;
      const label = getFieldLabel(rawName, t);
      items.push({ diagnosis: `${label}: ${fieldVal.value}`, related: t('formatLabels.oui') });
    }
    return items.slice(0, 10);
  }, [ef, t]);

  // Build gallery items for lightbox (all files with URLs + policy PDFs)
  const galleryItems: GalleryItem[] = useMemo(() => {
    if (!application?.id) return [];
    return evidenceItems.map(item => {
      if (item.isPolicyRef) {
        // Map policy reference names to API endpoints
        const pdfId = item.source.includes('Habitation') ? 'habitation' : 'sante';
        return {
          url: getMediaUrl(`/api/policy-pdfs/${pdfId}`),
          filename: item.source,
          type: 'pdf' as const,
          label: item.type,
        };
      }
      return {
        url: getMediaUrl(`/api/applications/${application.id}/files/${encodeURIComponent(item.source)}`),
        filename: item.source,
        type: item.fileType.icon as GalleryItem['type'],
        label: item.type,
      };
    });
  }, [evidenceItems, application?.id]);

  const tasks = useMemo(() => {
    const fmt = (offset: number) => {
      const d = new Date();
      d.setDate(d.getDate() + offset);
      return d.toLocaleDateString('fr-FR', { month: 'short', day: 'numeric' }).replace('.', '');
    };
    // Backend-driven tasks (from analysis output)
    const backendTasks: ContextTask[] = application?.context_tasks || [];
    if (backendTasks.length > 0) {
      return backendTasks.map((ct) => ({
        task: ct.task,
        due: fmt(ct.due_offset_days),
      }));
    }
    // Fallback: minimal tasks when no analysis has run yet
    return [
      { task: t('tasks.verifyCoverage'), due: fmt(0) },
      { task: t('tasks.mandateExpert'), due: fmt(1) },
      { task: t('tasks.applyFranchise'), due: fmt(3) },
    ];
  }, [application?.context_tasks, t]);

  const allTasksDone = checkedTasks.length === tasks.length;

  const handleGenerateNote = useCallback(() => {
    if (!allTasksDone || !application) return;
    generateNoteDeReglement({
      applicationId: application.id,
      insuredName: getFieldValue(ef, ['InsuredName', 'NomAssure', 'NomSouscripteur'], ''),
      policyNumber: getFieldValue(ef, ['PolicyNumber', 'NumeroPolice', 'NumeroContrat'], ''),
      claimNumber: getFieldValue(ef, ['ClaimNumber', 'NumeroSinistre'], application.id),
      claimDate: getFieldValue(ef, ['ClaimDate', 'DateSinistre', 'DateEvenement'], ''),
      causeOfLoss: getFieldValue(ef, ['CauseOfLoss', 'NatureSinistre', 'CauseDuSinistre'], 'Dégâts des eaux / Tempête'),
      propertyAddress: getFieldValue(ef, ['PropertyAddress', 'AdresseRisque', 'AdresseBien'], ''),
      lineOfBusiness: getFieldValue(ef, ['LineOfBusiness', 'NatureContrat', 'BrancheAssurance'], 'Habitation MRH'),
      totalEstimated: getFieldValue(ef, ['TotalIncurred', 'MontantEstime', 'MontantTotal', 'MontantDevis', 'MontantReparation'], '—'),
      deductible: '250 €',
      settlementAmount: getFieldValue(ef, ['SettlementAmount', 'MontantIndemnisation', 'IndemniteRecommandee'], ''),
      aiSummary: aiSummary,
      extractedFields: ef as Record<string, { field_name?: string; value?: unknown; confidence?: number }>,
      llmOutputs: llmOutputs,
      files: files.map(f => ({ filename: f.filename })),
      tasks: tasks.map((t, i) => ({ task: t.task, done: checkedTasks.includes(i) })),
    }, tReport, locale);
  }, [allTasksDone, application, ef, aiSummary, llmOutputs, files, tasks, checkedTasks, tReport, locale]);

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-slate-100">
      <HeaderStrip application={application} fraudResult={fraudResult} />

      {/* Decision bar — sticky below header */}
      {application && <UnderwritingDecisionFooter
        applicationId={application.id}
        position="top"
        onDecisionSubmitted={() => {
          // Refresh application to update timeline with the new decision action_history entry
          if (onApplicationUpdate) {
            getApplication(application.id).then(onApplicationUpdate).catch(() => {});
          }
        }}
      />}

      {/* Fraud analysis — surfaced right below the decision banner so the
          analyst sees fraud signals before opening the synthèse IA dialog. */}
      {application?.id && (
        <div className="mx-4 mt-2">
          <FraudAnalysisPanel applicationId={application.id} onFraudComplete={handleFraudComplete} />
        </div>
      )}

      {/* Communication Client — same banner placement as Fraud Analysis */}
      {application?.id && (
        <div className="mx-4 mt-1">
          <CommunicationClientPanel
            applicationId={application.id}
            insuredName={getFieldValue(ef, ['InsuredName', 'NomAssure', 'NomSouscripteur'], '')}
            claimReference={getFieldValue(ef, ['ClaimNumber', 'NumeroSinistre', 'ReferenceDossier'], application?.external_reference || application?.id || '')}
            decisionStatus={allTasksDone ? 'approved' : 'pending'}
            settlementAmount={getFieldValue(ef, ['SettlementAmount', 'MontantIndemnisation', 'IndemniteRecommandee', 'MontantEstime'], '')}
            boardLabel="Habitation MRH"
            severity={severityFromSentiment((application as any)?.sentiment_analysis)}
          />
        </div>
      )}

      {/* Customer 360 affiliation banner */}
      {application && !application.external_reference && (
        <CustomerAffiliationBanner
          applicationId={application.id}
          suggestedName={getFieldValue(ef, ['NomAssure', 'AssuréNom', 'NomSouscripteur'])}
          suggestedAddress={getFieldValue(ef, ['AdresseAssure', 'LieuSinistre'])}
          suggestedPhone={getFieldValue(ef, ['TelephoneAssure'])}
          suggestedEmail={getFieldValue(ef, ['EmailAssure'])}
          onAffiliated={() => { if (onApplicationUpdate && application) getApplication(application.id).then(onApplicationUpdate).catch(() => {}); }}
        />
      )}

      {/* Amount comparison warning */}
      {amountComparison?.hasOverclaim && (
        <div className="mx-4 mt-2 flex items-center gap-3 px-4 py-2.5 bg-amber-50 border border-amber-200 rounded-lg">
          <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
          <div className="flex-1 text-sm">
            <span className="font-medium text-amber-800">{t('amountComparison.warning')}</span>{' '}
            <span className="text-amber-700">
              {t('amountComparison.detail', { claimed: amountComparison.claimed.toLocaleString('fr-FR'), recommended: amountComparison.recommended.toLocaleString('fr-FR') })}
              {' '}(<span className="font-semibold">+{Math.abs(amountComparison.pctDelta).toFixed(0)}%</span>)
            </span>
          </div>
        </div>
      )}
      
      <div className="flex-1 min-h-0 overflow-auto p-4">
        <div className="min-h-0 flex flex-col gap-0 bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          
          {/* ROW 1: AI Notes | Extracted Data | Tasks */}
          <div className="grid min-h-0 flex-[1_1_35%] grid-cols-12 divide-x divide-slate-200">
            
            {/* AI Notes */}
            <div className="col-span-4 flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
                <Scale className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-slate-900 text-sm">{t('panels.aiSummary')}</span>
                {alertSignals.length > 0 && (
                  <span className={clsx('px-1.5 py-0.5 text-xs rounded-full font-medium', alertSignals.some(s => s.level === 'high') ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700')}>
                    {alertSignals.length} alerte{alertSignals.length > 1 ? 's' : ''}
                  </span>
                )}
                {aiSummary && !aiAnalyzing && (
                  <button
                    onClick={() => setAiDialogOpen(true)}
                    className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium text-indigo-600 hover:text-indigo-800 hover:bg-indigo-100 rounded transition-colors"
                    title={t('analysisDialog.relaunchTitle')}
                  >
                    <RefreshCw className="w-3 h-3" />
                    {t('analysis.relaunch')}
                  </button>
                )}
                <span className={clsx('text-xs text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded', !aiSummary || aiAnalyzing ? 'ml-auto' : '')}>
                  AI
                </span>
                <button onClick={() => setDetailDialog('synthese')} title={t('analysis.expand')} className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                  <Maximize2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-auto p-3 text-sm">
                {/* Alert signals — always show when available */}
                {alertSignals.length > 0 && (
                  <div className="space-y-1.5 mb-3">
                    {alertSignals.map((sig, idx) => (
                      <div
                        key={idx}
                        className={clsx(
                          'flex items-start gap-2 p-2 rounded-lg border text-xs',
                          sig.level === 'high' && 'bg-rose-50 border-rose-200 text-rose-800',
                          sig.level === 'medium' && 'bg-amber-50 border-amber-200 text-amber-800',
                          sig.level === 'low' && 'bg-blue-50 border-blue-200 text-blue-800',
                        )}
                      >
                        <AlertTriangle className={clsx('w-3.5 h-3.5 mt-0.5 flex-shrink-0', sig.level === 'high' ? 'text-rose-500' : sig.level === 'medium' ? 'text-amber-500' : 'text-blue-500')} />
                        <div className="flex-1 min-w-0">
                          <span className="font-semibold">{sig.label}</span>
                          <span className="ml-1 font-normal opacity-80">— {sig.detail}</span>
                          {sig.sourceUrl && (
                            <a href={sig.sourceUrl} target="_blank" rel="noopener noreferrer"
                               className="ml-1.5 inline-flex items-center gap-0.5 text-indigo-600 hover:text-indigo-800 hover:underline font-medium"
                               onClick={e => e.stopPropagation()}>
                              <ExternalLink className="w-3 h-3" />
                              <span>{sig.sourceTitle || 'Source'}</span>
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {aiSummary ? (
                  <>
                    <div className="relative">
                      <div className="space-y-1 text-xs max-h-[280px] overflow-hidden">
                        {aiSummary.split('\n').map((line, idx) => {
                          const colonIdx = line.indexOf(' : ');
                          if (colonIdx > 0 && colonIdx < 40) {
                            const label = line.slice(0, colonIdx);
                            const value = line.slice(colonIdx + 3);
                            const indent = label.length - label.trimStart().length;
                            return (
                              <div key={idx} className="flex gap-1" style={indent > 0 ? { paddingLeft: `${indent * 6}px` } : undefined}>
                                <span className="text-slate-500 font-medium flex-shrink-0">{label.trim()}</span>
                                <span className="text-slate-400 flex-shrink-0">:</span>
                                <span className="text-slate-800">{value}</span>
                              </div>
                            );
                          }
                          if (line.endsWith(':') || line.endsWith(' :')) {
                            return <div key={idx} className="text-indigo-700 font-semibold mt-2 mb-0.5">{line}</div>;
                          }
                          if (line.trim() === '') return <div key={idx} className="h-2" />;
                          return <div key={idx} className="text-slate-600">{line}</div>;
                        })}
                      </div>
                      <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-white via-white/80 to-transparent pointer-events-none" />
                    </div>
                    <button
                      onClick={() => setDetailDialog('synthese')}
                      className="mt-2 w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 transition-colors"
                    >
                      <Maximize2 className="w-3 h-3" />
                      {t('panels.viewFullAnalysis')}
                    </button>
                  </>
                ) : aiAnalyzing ? (
                  <div className="flex flex-col items-center justify-center h-full gap-3 text-center py-4">
                    <Loader2 className="w-6 h-6 text-indigo-500 animate-spin" />
                    <p className="text-xs text-indigo-600 font-medium">{t('analysis.inProgress')}</p>
                    <p className="text-xs text-slate-400">{t('analysis.willAppear')}</p>
                  </div>
                ) : aiError ? (
                  <div className="flex flex-col items-center justify-center h-full gap-2 text-center py-4">
                    <AlertTriangle className="w-5 h-5 text-rose-400" />
                    <p className="text-xs text-rose-600">{aiError}</p>
                    <button
                      onClick={() => { setAiError(null); setAiDialogOpen(true); }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 transition-colors"
                    >
                      <Activity className="w-3.5 h-3.5" />
                      {t('analysis.retry')}
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full gap-2 text-center py-4">
                    <Activity className="w-5 h-5 text-slate-300" />
                    <p className="text-xs text-slate-400">{t('analysis.notRun')}</p>
                    <button
                      onClick={() => setAiDialogOpen(true)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 transition-colors"
                    >
                      <Activity className="w-3.5 h-3.5" />
                      {t('analysis.launch')}
                    </button>
                  </div>
                )}
              </div>
              {/* Fraud Analysis moved up — now surfaced below decision banner */}
            </div>
            
            {/* Extracted Fields / Analyzer Schema (toggle) */}
            <div className="col-span-4 flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
                <TrendingUp className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-slate-900 text-sm">
                  {showSchema ? t('cuSchema.title') : t('panels.information')}
                </span>
                <button
                  onClick={() => setShowSchema(!showSchema)}
                  className="ml-auto flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 transition-colors"
                  title={showSchema ? t('cuSchema.viewData') : t('cuSchema.viewSchema')}
                >
                  <Layers className="w-3.5 h-3.5" />
                  {showSchema ? t('cuSchema.dataLabel') : t('cuSchema.schemaLabel')}
                </button>
                <button onClick={() => setDetailDialog('infos')} title={t('analysis.expand')} className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                  <Maximize2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-auto p-3 text-xs">
                {showSchema ? (
                  analyzerSchema ? (
                    <div className="space-y-1">
                      <div className="text-slate-500 mb-2">{analyzerSchema.field_count} champs définis — <span className="font-mono text-xs">{analyzerSchema.schema.name}</span></div>
                      {Object.entries(analyzerSchema.schema.fields).map(([fieldName, field]) => (
                        <div key={fieldName} className="flex items-start justify-between py-1 border-b border-slate-50 last:border-0">
                          <div className="min-w-0 flex-1">
                            <div className="font-mono text-xs font-medium text-slate-900">{fieldName}</div>
                            <div className="text-slate-500 truncate" title={field.description}>{field.description}</div>
                          </div>
                          <span className="ml-2 px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-xs flex-shrink-0">{field.type}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">
                      <Layers className="w-6 h-6 mx-auto mb-1" />
                      <p>{t('cuSchema.loading')}</p>
                    </div>
                  )
                ) : Object.keys(ef).length > 0 ? (
                  <div className="space-y-1">
                    {Object.entries(ef).filter(([key]) => {
                      const rawName = key.split(':').pop() || key;
                      return DOSSIER_FIELDS.has(rawName);
                    }).slice(0, 10).map(([key, val]) => {
                      const fieldVal = val as { field_name?: string; value?: unknown; confidence?: number } | undefined;
                      if (!fieldVal || fieldVal.value == null || fieldVal.value === '') return null;
                      // Sanitise: a stored value can occasionally be a leaked HTML fragment (e.g. "</td>").
                      const displayValue = String(fieldVal.value).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
                      if (!displayValue) return null;
                      const rawName = fieldVal.field_name || key.split(':').pop() || key;
                      const label = getFieldLabel(rawName, t);
                      const isNameField = rawName === 'NomAssure' || rawName === 'AssuréNom' || rawName === 'NomSouscripteur';
                      const custId = application?.external_reference || matchedCustomerId;
                      return (
                        <div key={key} className="flex justify-between items-center">
                          <span className="text-slate-600 truncate mr-2">{label}</span>
                          {isNameField && custId ? (
                            <a href={`/customers/${custId}`} className="font-medium text-indigo-600 hover:text-indigo-800 underline text-right flex-shrink-0 cursor-pointer">{displayValue}</a>
                          ) : (
                            <span className="font-medium text-slate-900 text-right flex-shrink-0">{displayValue}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : markdownDerivedFields.length > 0 ? (
                  <div className="space-y-1">
                    {markdownDerivedFields.map((field, i) => (
                      <div key={i} className="flex justify-between items-center">
                        <span className="text-slate-600 truncate mr-2">{field.name}</span>
                        <span className="font-medium text-slate-900 text-right flex-shrink-0 max-w-[60%] truncate">{field.value}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-4 text-slate-400">
                    <p>{t('cuSchema.noFields')}</p>
                    <p className="text-xs mt-1">{t('cuSchema.launchExtraction')}</p>
                  </div>
                )}
              </div>
            </div>
            
            {/* Tasks + Actions + Communication */}
            <div className="col-span-4 flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
                <ListChecks className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-slate-900 text-sm">{t('panels.actionsAndTasks')}</span>
                <span className="ml-auto text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">{tasks.length - checkedTasks.length} {t('tasks.pending')}</span>
                <button onClick={() => setDetailDialog('tasks')} title={t('analysis.expand')} className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                  <Maximize2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-auto p-3 space-y-3">
                {/* Next Best Action */}
                <NextBestActionPanel
                  extractedFields={ef}
                  llmOutputs={llmOutputs}
                  fraudResult={fraudResult}
                  estimatedAmount={parseFloat(String(getFieldValue(ef, ['MontantEstime', 'TotalIncurred', 'MontantTotal'], '0')).replace(/[^\d.,]/g, '').replace(',', '.')) || 0}
                  analysisComplete={!!aiSummary && !aiAnalyzing}
                />

                {/* Client Sentiment */}
                <ClientSentimentPanel
                  customerData={customerData}
                  claimNature={getFieldValue(ef, ['NatureSinistre', 'CauseOfLoss', 'CauseDuSinistre'], 'Dégâts des eaux')}
                  estimatedAmount={parseFloat(String(getFieldValue(ef, ['MontantEstime', 'TotalIncurred', 'MontantTotal'], '0')).replace(/[^\d.,]/g, '').replace(',', '.')) || 0}
                  daysSinceClaim={application?.created_at ? Math.floor((Date.now() - new Date(application.created_at).getTime()) / 86400000) : 0}
                  backendSentiment={(application as any)?.sentiment_analysis ?? null}
                  mode="compact"
                  onExpand={() => setDetailDialog('sentiment')}
                />

                {/* Task checklist */}
                <div className="space-y-2">
                  {tasks.map((t, i) => (
                    <label key={i} className="flex items-center gap-2 cursor-pointer text-sm">
                      <input type="checkbox" checked={checkedTasks.includes(i)} onChange={() => setCheckedTasks(prev => prev.includes(i) ? prev.filter(x => x !== i) : [...prev, i])} className="w-3.5 h-3.5 rounded border-slate-300 text-indigo-600" />
                      <span className={clsx('flex-1', checkedTasks.includes(i) ? 'text-slate-400 line-through' : 'text-slate-900')}>{t.task}</span>
                      <span className="text-xs text-slate-400">{t.due}</span>
                    </label>
                  ))}
                </div>
                <button
                  onClick={handleGenerateNote}
                  disabled={!allTasksDone || fraudResult?.overall_assessment?.siu_referral_recommended === true}
                  className={clsx(
                    'w-full py-2 text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2',
                    fraudResult?.overall_assessment?.siu_referral_recommended
                      ? 'bg-rose-400 cursor-not-allowed'
                      : allTasksDone
                      ? 'bg-indigo-600 hover:bg-indigo-700 cursor-pointer'
                      : 'bg-slate-300 cursor-not-allowed'
                  )}
                  title={
                    fraudResult?.overall_assessment?.siu_referral_recommended
                      ? 'Renvoi SIU recommandé — règlement suspendu'
                      : allTasksDone ? 'Générer le PDF de note de règlement' : 'Cochez toutes les tâches pour activer'
                  }
                >
                  <FileDown className="w-4 h-4" />
                  {fraudResult?.overall_assessment?.siu_referral_recommended
                    ? t('panels.siuSuspended')
                    : t('panels.settlementNote')}
                </button>

                {/* Communication Generator */}
                <div className="border-t border-slate-100 pt-3">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">{t('panels.clientCommunication')}</div>
                  <CommunicationGenerator
                    applicationId={application?.id || ''}
                    insuredName={getFieldValue(ef, ['InsuredName', 'NomAssure', 'NomSouscripteur'], '')}
                    claimReference={getFieldValue(ef, ['ClaimNumber', 'NumeroSinistre', 'ReferenceDossier'], application?.external_reference || application?.id || '')}
                    decisionStatus={allTasksDone ? 'approved' : 'pending'}
                    settlementAmount={getFieldValue(ef, ['SettlementAmount', 'MontantIndemnisation', 'IndemniteRecommandee', 'MontantEstime'], '')}
                  />
                </div>
              </div>
            </div>
          </div>
          
          {/* ROW 2: Timeline | Damages */}
          <div className="grid min-h-0 flex-[1_1_30%] grid-cols-12 divide-x divide-slate-200 border-t border-slate-200">
            <div className="col-span-6 flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
                <Activity className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-slate-900 text-sm">{t('panels.chronology')}</span>
                <button onClick={() => setDetailDialog('timeline')} title={t('analysis.expand')} className="ml-auto p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                  <Maximize2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-auto p-3">
                <div className="space-y-2">
                  {liabilityEvents.map((e, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <div className="w-10 text-slate-400 flex-shrink-0">{e.date}</div>
                      <div className={clsx('w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0', e.impact === 'supports' ? 'bg-emerald-500' : e.impact === 'disputes' ? 'bg-rose-500' : 'bg-slate-300')} />
                      <div className="min-w-0">
                        <div className="font-medium text-slate-900">{e.type}</div>
                        <div className="text-slate-500 truncate">{e.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            
            <div className="col-span-6 flex flex-col overflow-hidden border-l-4 border-l-amber-400">
              <div className="px-3 py-2 border-b border-amber-200 flex items-center gap-2 bg-amber-50 flex-shrink-0">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                <span className="font-semibold text-slate-900 text-sm">{t('panels.damagesFound')}</span>
                <button onClick={() => setDetailDialog('damages')} title={t('analysis.expand')} className="ml-auto p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                  <Maximize2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-auto p-3">
                {injuries.length > 0 ? (
                  <table className="w-full text-xs">
                    <thead><tr className="text-slate-500 border-b"><th className="text-left py-1.5 font-normal">{t('documents.zoneDamage')}</th><th className="text-left py-1.5 font-normal">{t('documents.relatedToClaim')}</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {injuries.map((inj, i) => (
                        <tr key={i}>
                          <td className="py-2 text-slate-900">{inj.diagnosis}</td>
                          <td className="py-2"><span className={clsx('px-1.5 py-0.5 rounded text-xs', inj.related === 'Oui' ? 'bg-emerald-100 text-emerald-700' : inj.related === 'Possible' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600')}>{inj.related}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : markdownDerivedDamages.length > 0 ? (
                  <table className="w-full text-xs">
                    <thead><tr className="text-slate-500 border-b"><th className="text-left py-1.5 font-normal">{t('damages.damageItem')}</th><th className="text-left py-1.5 font-normal">{t('damages.linked')}</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {markdownDerivedDamages.map((dmg, i) => (
                        <tr key={i}>
                          <td className="py-2 text-slate-900">{dmg.description}</td>
                          <td className="py-2"><span className="px-1.5 py-0.5 rounded text-xs bg-emerald-100 text-emerald-700">{dmg.related}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="text-center py-4 text-slate-400 text-xs">
                    <p>{t('documents.noDamageDetected')}</p>
                    <p className="mt-1">{t('documents.damageWillAppear')}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
          
          {/* ROW 3: Evidence from actual files */}
          <div className="min-h-0 flex-[1_1_35%] flex flex-col overflow-hidden border-t border-slate-200">
            <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
              <FileText className="w-4 h-4 text-indigo-600" />
              <span className="font-semibold text-slate-900 text-sm">{t('panels.documents')}</span>
              <span className="ml-auto text-xs text-slate-500">{evidenceItems.length} {t('documents.pieces')}</span>
              <input ref={fileInputRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx" className="hidden" onChange={(e) => handleAddFiles(e.target.files)} />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadingFiles}
                className={clsx(
                  'ml-2 flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all',
                  uploadingFiles
                    ? 'bg-slate-200 text-slate-400 cursor-wait'
                    : 'bg-emerald-600 text-white hover:bg-emerald-700'
                )}
              >
                {uploadingFiles ? (
                  <><Loader2 className="w-3 h-3 animate-spin" /> {progressMessage || t('documents.processing')}</>
                ) : (
                  <><Upload className="w-3 h-3" /> {t('documents.addFiles')}</>
                )}
              </button>
            </div>
            <div className="flex-1 overflow-auto">
              {evidenceItems.length > 0 ? (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr className="text-xs text-slate-500">
                      <th className="px-4 py-2 text-left w-1/4">{t('documents.sourceDocument')}</th>
                      <th className="px-4 py-2 text-left w-1/6">{t('documents.type')}</th>
                      <th className="px-4 py-2 text-center w-1/6">{t('documents.confirms')}</th>
                      <th className="px-4 py-2 text-center w-1/6">{t('documents.contradicts')}</th>
                      <th className="px-4 py-2 text-left">{t('documents.summary')}</th>
                      <th className="px-4 py-2 text-center w-16">{t('documents.view')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {evidenceItems.map((item, i) => {
                      // Cross-reference with fraud image analysis
                      const imgAnalysis = fraudResult?.image_analyses?.find(
                        ia => ia.filename === item.source || item.source.includes(ia.filename) || ia.filename.includes(item.source)
                      );
                      return (
                      <tr key={i} className="hover:bg-slate-50 cursor-pointer" onClick={() => setLightboxIndex(i)}>
                        <td className="px-4 py-2.5 text-slate-900">
                          <div className="flex items-center gap-2">
                            {item.fileType.icon === 'image' ? <Image className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" /> :
                             item.fileType.icon === 'video' ? <Film className="w-3.5 h-3.5 text-purple-500 flex-shrink-0" /> :
                             <FileText className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />}
                            <span className="truncate text-indigo-600 hover:underline">{item.source}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5"><span className="px-2 py-0.5 rounded text-xs bg-purple-100 text-purple-700">{item.type}</span></td>
                        <td className="px-4 py-2.5 text-center">{item.supports && <CheckCircle className="w-4 h-4 text-emerald-500 mx-auto" />}</td>
                        <td className="px-4 py-2.5 text-center">{item.challenges && <CheckCircle className="w-4 h-4 text-rose-500 mx-auto" />}</td>
                        <td className="px-4 py-2.5 text-slate-600 text-xs">
                          <div className="flex items-center gap-2">
                            <span className="flex-1">{item.summary}</span>
                            {/* Image authenticity badge from fraud analysis */}
                            {imgAnalysis && !imgAnalysis.error && (
                              <div className="relative group/auth flex-shrink-0">
                                {imgAnalysis.is_likely_authentic ? (
                                  <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                                    <CheckCircle className="w-3 h-3" />
                                    {Math.round((imgAnalysis.authenticity_score || 0) * 100)}%
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-50 text-rose-700 border border-rose-200">
                                    <AlertTriangle className="w-3 h-3" />
                                    {Math.round((imgAnalysis.authenticity_score || 0) * 100)}%
                                  </span>
                                )}
                                {/* Tooltip with manipulation details */}
                                {imgAnalysis.manipulation_indicators && imgAnalysis.manipulation_indicators.length > 0 && (
                                  <div className="absolute right-0 top-full mt-1 z-50 w-64 bg-white text-slate-800 rounded-lg shadow-xl border border-slate-200 p-2.5 opacity-0 invisible group-hover/auth:opacity-100 group-hover/auth:visible transition-all duration-200 pointer-events-none group-hover/auth:pointer-events-auto">
                    <div className="text-[10px] font-semibold text-slate-500 uppercase mb-1">{t('documents.indicators')}</div>
                                    {imgAnalysis.manipulation_indicators.map((ind, j) => (
                                      <div key={j} className="flex items-start gap-1.5 text-[11px] text-slate-600 mt-1">
                                        <AlertTriangle className="w-3 h-3 text-amber-500 mt-0.5 flex-shrink-0" />
                                        <span>{ind.description || ind.indicator}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          {application?.id && (
                            <button
                              onClick={(e) => { e.stopPropagation(); setLightboxIndex(i); }}
                              className="text-indigo-600 hover:text-indigo-700"
                              title={`Voir ${item.source}`}
                            >
                              <ZoomIn className="w-4 h-4 mx-auto" />
                            </button>
                          )}
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="text-center py-8 text-slate-400">
                  <FileText className="w-8 h-8 mx-auto mb-2" />
                  <p>{t('documents.noDocuments')}</p>
                </div>
              )}
            </div>
          </div>
          
        </div>
      </div>

      {/* Gallery lightbox */}
      {lightboxIndex !== null && galleryItems.length > 0 && (
        <GalleryLightbox
          items={galleryItems}
          currentIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />
      )}

      {/* AI Analysis dialog */}
      {aiDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={handleAiDialogBackdropClick}>
          <div ref={aiDialogRef} className="bg-white rounded-xl shadow-2xl w-full max-w-xl lg:max-w-2xl max-h-[70vh] flex flex-col overflow-hidden">
            {/* Header */}
            <div className="px-6 py-4 bg-slate-50 border-b border-slate-100 flex items-center gap-3 flex-shrink-0">
              <div className="w-9 h-9 rounded-lg bg-indigo-100 flex items-center justify-center text-indigo-600">
                <Scale className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <h2 className="text-base font-semibold text-slate-900">{t('analysis.liability')}</h2>
                <p className="text-xs text-slate-500">{t('analysis.liabilityDescription')}</p>
              </div>
              <button onClick={() => setAiDialogOpen(false)} title={t('damages.close')} className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-auto p-6 space-y-4">
              {/* What will be analysed */}
              <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4 text-xs text-indigo-700">
                <p className="font-semibold mb-2">{t('analysis.launchDescription')}</p>
                <ul className="space-y-1.5 list-disc list-inside">
                  <li>{t('analysisDialog.bullet1')}</li>
                  <li>{t('analysisDialog.bullet2')}</li>
                  <li>{t('analysisDialog.bullet3')}</li>
                  <li>{t('analysisDialog.bullet4')}</li>
                  <li>{t('analysisDialog.bullet5')}</li>
                </ul>
                <p className="mt-3 text-indigo-600 font-medium">⏱ {t('analysisDialog.duration')}</p>
              </div>

              {/* Liability assessment preview */}
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <div className="px-4 py-2.5 flex items-center justify-between bg-slate-50 cursor-pointer" onClick={() => setExpandedSection(expandedSection === 'liability' ? '' : 'liability')}>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-slate-900">{t('analysis.liabilityTitle')}</span>
                    <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 text-xs rounded">{t('analysis.climateEvent')}</span>
                  </div>
                  {expandedSection === 'liability' ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                </div>
                {expandedSection === 'liability' && (
                  <div className="px-4 py-3 text-slate-600 text-xs border-t border-slate-100">
                    {aiSummary || t('analysisDialog.waitingForAnalysis')}
                  </div>
                )}
              </div>

              {/* Alert signals preview */}
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <div className="px-4 py-2.5 flex items-center justify-between bg-slate-50 cursor-pointer" onClick={() => setExpandedSection(expandedSection === 'redflags' ? '' : 'redflags')}>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-slate-900">{t('analysis.alertSignals')}</span>
                    {alertSignals.length > 0 ? (
                      <span className={clsx('px-1.5 py-0.5 text-xs rounded', alertSignals.some(s => s.level === 'high') ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700')}>
                        {alertSignals.length} {t('analysis.signalCount', { count: alertSignals.length })}
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 text-xs rounded">{t('analysis.noSignals')}</span>
                    )}
                  </div>
                  {expandedSection === 'redflags' ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                </div>
                {expandedSection === 'redflags' && (
                  <div className="px-4 py-3 space-y-1.5 border-t border-slate-100">
                    {alertSignals.length > 0 ? alertSignals.map((signal, i) => (
                      <div key={i} className={clsx('flex items-start gap-2 text-xs p-1.5 rounded', signal.level === 'high' ? 'bg-rose-50' : signal.level === 'medium' ? 'bg-amber-50' : 'bg-blue-50')}>
                        <span className={clsx('w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0', signal.level === 'high' ? 'bg-rose-500' : signal.level === 'medium' ? 'bg-amber-500' : 'bg-blue-500')} />
                        <div>
                          <span className="font-medium text-slate-900">{signal.label}</span>
                          <p className="text-slate-600 mt-0.5">{signal.detail}</p>
                        </div>
                      </div>
                    )) : (
                      <div className="text-slate-500 text-xs">{t('analysis.noSignalsDetail')}</div>
                    )}
                  </div>
                )}
              </div>

              {/* Error */}
              {aiError && (
                <div className="flex items-center gap-2 text-sm text-rose-600 bg-rose-50 p-3 rounded-lg border border-rose-200">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  {aiError}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex items-center justify-end gap-3 flex-shrink-0">
              <button
                onClick={() => setAiDialogOpen(false)}
                className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                {t('analysis.cancel')}
              </button>
              <button
                onClick={handleLaunchAnalysis}
                disabled={aiLoading || !application?.document_markdown}
                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
              >
                {aiLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
                {aiLoading ? t('analysis.progressMessage') : t('analysis.launch')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail dialogs for each section */}
      {detailDialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50" onClick={() => setDetailDialog(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl 2xl:max-w-6xl max-h-[90vh] flex flex-col overflow-hidden mx-4" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between flex-shrink-0">
              <h2 className="text-base font-semibold text-slate-900">
                {detailDialog === 'synthese' && t('panels.aiSummary')}
                {detailDialog === 'infos' && t('analysis.dossierInfo')}
                {detailDialog === 'tasks' && t('analysis.tasksTitle')}
                {detailDialog === 'timeline' && t('panels.chronology')}
                {detailDialog === 'damages' && t('panels.damagesFound')}
                {detailDialog === 'sentiment' && t('panels.clientSentiment')}
              </h2>
              <button onClick={() => setDetailDialog(null)} className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-6">

              {/* Synthèse IA expanded — tabbed view */}
              {detailDialog === 'synthese' && (() => {
                const parsed = parseAiSummary(aiSummary || '');
                const TABS: Array<{ key: typeof syntheseTab; label: string }> = [
                  { key: 'overview', label: t('analysis.tabOverview') },
                  { key: 'damages', label: t('analysis.tabDamages') },
                  { key: 'decision', label: t('analysis.tabDecision') },
                  { key: 'risk', label: t('analysis.tabRisk') },
                  { key: 'timeline', label: t('analysis.tabTimeline') },
                  { key: 'raw', label: t('analysis.tabRaw') },
                ];
                const renderText = (content: string) => (
                  <div className="text-sm leading-relaxed text-slate-700 prose prose-sm max-w-none prose-headings:text-indigo-700 prose-headings:font-semibold prose-headings:mt-3 prose-headings:mb-1 prose-strong:text-slate-900 prose-strong:font-semibold prose-em:italic prose-ul:my-1 prose-li:my-0.5 prose-p:my-1">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={SYNTHESE_MARKDOWN_COMPONENTS}>
                      {content}
                    </ReactMarkdown>
                  </div>
                );
                return (
                  <div className="space-y-4">
                    {alertSignals.length > 0 && syntheseTab !== 'raw' && (
                      <div className="space-y-2">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">{t('analysis.alerts')}</h3>
                        {alertSignals.map((sig, idx) => (
                          <div key={idx} className={clsx('flex items-start gap-3 p-3 rounded-lg border text-sm',
                            sig.level === 'high' && 'bg-rose-50 border-rose-200 text-rose-800',
                            sig.level === 'medium' && 'bg-amber-50 border-amber-200 text-amber-800',
                            sig.level === 'low' && 'bg-blue-50 border-blue-200 text-blue-800',
                          )}>
                            <AlertTriangle className={clsx('w-5 h-5 mt-0.5 flex-shrink-0', sig.level === 'high' ? 'text-rose-500' : sig.level === 'medium' ? 'text-amber-500' : 'text-blue-500')} />
                            <div><span className="font-semibold">{sig.label}</span><span className="ml-2 font-normal opacity-80">{sig.detail}</span></div>
                          </div>
                        ))}
                      </div>
                    )}
                    {/* Tab navigation */}
                    <div className="flex flex-wrap gap-1 border-b border-slate-200">
                      {TABS.map(tab => (
                        <button
                          key={tab.key}
                          onClick={() => setSyntheseTab(tab.key)}
                          className={clsx(
                            'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
                            syntheseTab === tab.key
                              ? 'border-indigo-600 text-indigo-700'
                              : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                          )}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                    {/* Tab content */}
                    <div className="bg-slate-50 p-4 rounded-lg min-h-[200px]">
                      {syntheseTab === 'raw' ? (
                        aiSummary
                          ? renderText(aiSummary)
                          : <p className="text-sm text-slate-400 italic">{t('analysis.noContent')}</p>
                      ) : syntheseTab === 'damages' ? (
                        // Structured damages table — uses the same parsed data
                        // as the "Dommages" detail dialog so the modal stays
                        // readable instead of a single run-on paragraph.
                        (injuries.length > 0 || markdownDerivedDamages.length > 0) ? (
                          <table className="w-full text-sm border-collapse bg-white rounded-lg overflow-hidden">
                            <thead>
                              <tr className="bg-slate-100">
                                <th className="text-left p-3 border-b font-medium text-slate-700">Zone / Bien / Dommage</th>
                                <th className="text-left p-3 border-b font-medium text-slate-700 w-32">Lié au sinistre&nbsp;?</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {injuries.map((inj, i) => (
                                <tr key={`inj-${i}`} className="even:bg-slate-50">
                                  <td className="p-3 text-slate-900">{inj.diagnosis}</td>
                                  <td className="p-3"><span className={clsx('px-2 py-1 rounded text-xs font-medium', inj.related === 'Oui' ? 'bg-emerald-100 text-emerald-700' : inj.related === 'Possible' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600')}>{inj.related}</span></td>
                                </tr>
                              ))}
                              {markdownDerivedDamages.map((dmg, i) => (
                                <tr key={`md-${i}`} className="even:bg-slate-50">
                                  <td className="p-3 text-slate-900">{dmg.description}</td>
                                  <td className="p-3"><span className="px-2 py-1 rounded text-xs font-medium bg-emerald-100 text-emerald-700">{dmg.related}</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : parsed.damages ? (
                          // Fallback to formatted markdown when no structured items extracted
                          renderText(parsed.damages)
                        ) : (
                          <p className="text-sm text-slate-400 italic">{t('analysis.noContent')}</p>
                        )
                      ) : syntheseTab === 'timeline' ? (
                        // Reuse the page-level ChronologicalOverview so the
                        // modal stays in sync with the main "Chronologie" tab.
                        application ? (
                          <div className="-mx-4 -my-4">
                            <ChronologicalOverview application={application} fullWidth />
                          </div>
                        ) : (
                          <p className="text-sm text-slate-400 italic">{t('analysis.noContent')}</p>
                        )
                      ) : (
                        parsed[syntheseTab]
                          ? renderText(parsed[syntheseTab])
                          : <p className="text-sm text-slate-400 italic">{t('analysis.noContent')}</p>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Informations expanded */}
              {detailDialog === 'infos' && (
                <div>
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-slate-100">
                      {(() => {
                        const rows = Object.entries(ef)
                          .filter(([key]) => {
                            const rawName = key.split(':').pop() || key;
                            return DOSSIER_FIELDS.has(rawName);
                          })
                          .map(([key, val]) => {
                            const fieldVal = val as { field_name?: string; value?: unknown; confidence?: number } | undefined;
                            const value = textValue(fieldVal?.value);
                            if (!fieldVal || !value) return null;
                            const rawName = fieldVal.field_name || key.split(':').pop() || key;
                            const label = getFieldLabel(rawName, t);
                            return (
                              <tr key={key}>
                                <td className="py-3 pr-4 text-slate-500 font-medium w-1/3">{label}</td>
                                <td className="py-3 text-slate-900">{value}</td>
                                {fieldVal.confidence != null && <td className="py-3 text-right text-xs text-slate-400">{Math.round(fieldVal.confidence * 100)}%</td>}
                              </tr>
                            );
                          })
                          .filter(Boolean);
                        if (rows.length > 0) return rows;
                        return markdownDerivedFields.map((field) => (
                          <tr key={field.name}>
                            <td className="py-3 pr-4 text-slate-500 font-medium w-1/3">{field.name}</td>
                            <td className="py-3 text-slate-900">{field.value}</td>
                            <td className="py-3 text-right text-xs text-slate-400">—</td>
                          </tr>
                        ));
                      })()}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Tâches expanded */}
              {detailDialog === 'tasks' && (
                <div className="space-y-3">
                  {tasks.map((t, i) => (
                    <label key={i} className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer">
                      <input type="checkbox" checked={checkedTasks.includes(i)} onChange={() => setCheckedTasks(prev => prev.includes(i) ? prev.filter(x => x !== i) : [...prev, i])} className="w-4 h-4 rounded border-slate-300 text-indigo-600" />
                      <span className={clsx('flex-1 text-sm', checkedTasks.includes(i) ? 'text-slate-400 line-through' : 'text-slate-900')}>{t.task}</span>
                      <span className="text-sm text-slate-400">{t.due}</span>
                    </label>
                  ))}
                </div>
              )}

              {/* Chronologie expanded */}
              {detailDialog === 'timeline' && (
                <div className="space-y-4">
                  {liabilityEvents.map((e, i) => (
                    <div key={i} className="flex items-start gap-4 p-3 rounded-lg border border-slate-100">
                      <div className="w-14 text-sm font-medium text-slate-500 flex-shrink-0">{e.date}</div>
                      <div className={clsx('w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0',
                        e.impact === 'supports' ? 'bg-emerald-500' : e.impact === 'disputes' ? 'bg-rose-500' : 'bg-slate-300')} />
                      <div>
                        <div className="text-sm font-medium text-slate-900">{e.type}</div>
                        <div className="text-sm text-slate-500 mt-0.5">{e.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Dommages expanded */}
              {detailDialog === 'damages' && (
                <div>
                  {(injuries.length > 0 || markdownDerivedDamages.length > 0) ? (
                    <table className="w-full text-sm border-collapse">
                      <thead><tr className="bg-slate-50"><th className="text-left p-3 border-b font-medium text-slate-700">Zone / Bien / Dommage</th><th className="text-left p-3 border-b font-medium text-slate-700 w-32">Lié au sinistre ?</th></tr></thead>
                      <tbody className="divide-y divide-slate-100">
                        {injuries.map((inj, i) => (
                          <tr key={i}>
                            <td className="p-3 text-slate-900">{inj.diagnosis}</td>
                            <td className="p-3"><span className={clsx('px-2 py-1 rounded text-xs font-medium', inj.related === 'Oui' ? 'bg-emerald-100 text-emerald-700' : inj.related === 'Possible' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600')}>{inj.related}</span></td>
                          </tr>
                        ))}
                        {markdownDerivedDamages.map((dmg, i) => (
                          <tr key={`md-${i}`}>
                            <td className="p-3 text-slate-900">{dmg.description}</td>
                            <td className="p-3"><span className="px-2 py-1 rounded text-xs font-medium bg-emerald-100 text-emerald-700">{dmg.related}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="text-center py-8 text-slate-400">
                      <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
                      <p>{t('damages.noDamageDetected')}</p>
                    </div>
                  )}
                </div>
              )}

              {/* Sentiment expanded */}
              {detailDialog === 'sentiment' && (
                <ClientSentimentPanel
                  customerData={customerData}
                  claimNature={getFieldValue(ef, ['NatureSinistre', 'CauseOfLoss', 'CauseDuSinistre'], 'Dégâts des eaux')}
                  estimatedAmount={parseFloat(String(getFieldValue(ef, ['MontantEstime', 'TotalIncurred', 'MontantTotal'], '0')).replace(/[^\d.,]/g, '').replace(',', '.')) || 0}
                  daysSinceClaim={application?.created_at ? Math.floor((Date.now() - new Date(application.created_at).getTime()) / 86400000) : 0}
                  backendSentiment={(application as any)?.sentiment_analysis ?? null}
                  mode="full"
                />
              )}

            </div>
          </div>
        </div>
      )}

    </div>
  );
}
