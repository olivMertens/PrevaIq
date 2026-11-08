'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { ChevronDown, ChevronUp, FileText } from 'lucide-react';
import type { ApplicationMetadata } from '@/lib/types';
import { brand, isWorkbenchSystem } from '@/lib/brand';
import { formatAmount, type CurrencyCode } from '@/lib/currency';
import { useApplicationCurrency } from '@/lib/CurrencyProvider';
import { formatTimelineDate, parseTimelineDate } from '@/lib/timelineDates';
import { humanizeFieldKey, markdownPreview } from './claims/property/analysisMarkdown';
import MarkdownText from './claims/property/MarkdownText';
import ConfidenceIndicator from './ConfidenceIndicator';
import clsx from 'clsx';

interface ChronologicalOverviewProps {
  application: ApplicationMetadata;
  fullWidth?: boolean;
  persona?: string;
}

interface TimelineEntry {
  date: string;
  year: string;
  title: string;
  description?: string;
  color: 'orange' | 'yellow' | 'blue' | 'green' | 'purple' | 'red';
  details?: string;
  sortDate?: number;
  confidence?: number;
}

const parseDate = parseTimelineDate;
const formatDateDisplay = formatTimelineDate;

type Translate = (key: string, values?: Record<string, string | number | Date>) => string;

// Analysis sections with a translated name (chronological.sections); others are humanized.
const TRANSLATED_SECTIONS = new Set([
  'application_summary', 'medical_summary', 'requirements', 'clinical_case_notes',
  'clinical_timeline', 'benefits_policy', 'claim_line_evaluation', 'tasks_decisions',
  'damage_assessment', 'liability_assessment', 'fraud_detection', 'payout_recommendation',
  'liability_case_notes', 'incident_timeline', 'injury_treatment', 'evidence_matrix',
  'damages_negotiation', 'tasks_next_steps', 'decision',
]);

function analysisSectionLabel(section: string, t: Translate): string {
  return TRANSLATED_SECTIONS.has(section) ? t(`sections.${section}`) : humanizeFieldKey(section);
}

function getStringValue(field: any): string {
  if (!field) return '';
  if (typeof field === 'string') return field;
  if (field.valueString) return field.valueString;
  if (field.content) return field.content;
  if (field.text) return field.text;
  return '';
}

function buildTimelineFromData(application: ApplicationMetadata, locale: string, t: (key: string) => string): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  const fields = application.extracted_fields || {};
  
  // Get confidence from underlying extracted fields
  const medicalField = Object.values(fields).find(f => f.field_name === 'MedicalConditionsSummary');
  const medicalConfidence = medicalField?.confidence;

  // First, try LLM outputs for conditions from other_medical_findings
  const llmOtherFindings = application.llm_outputs?.medical_summary?.other_medical_findings?.parsed as any;
  if (llmOtherFindings?.conditions && Array.isArray(llmOtherFindings.conditions)) {
    llmOtherFindings.conditions.forEach((condition: any, idx: number) => {
      const name = condition.name || t('unknownCondition');
      const onset = condition.onset || '';
      const status = condition.status || '';
      const details = condition.details || '';
      
      const statusLabel = status === 'Ongoing' ? t('statusOngoing') : status === 'Resolved' ? t('statusResolved') : status === 'active' ? t('statusActive') : status === 'monitoring' ? t('statusMonitoring') : status;
      const title = `${name}${statusLabel ? ' (' + statusLabel + ')' : ''}`;
      const fullDetails = `${name}\n${t('onsetLabel')} ${onset}\n${t('statusLabel')} ${statusLabel}\n${t('detailsLabel')} ${details}`;
      
      const parsedDate = parseDate(onset);
      const displayDate = formatDateDisplay(parsedDate, locale);
      
      entries.push({
        date: displayDate.date,
        year: displayDate.year,
        title: title.substring(0, 50) + (title.length > 50 ? '...' : ''),
        description: title,
        color: ['orange', 'yellow', 'blue', 'green', 'purple'][idx % 5] as TimelineEntry['color'],
        details: fullDetails,
        sortDate: parsedDate?.getTime() || 0,
        confidence: medicalConfidence,
      });
    });
  } else {
    // Fall back to extracted fields - Parse medical conditions (string format)
    if (medicalField?.value) {
      const conditions = String(medicalField.value).split(';').map(s => s.trim()).filter(Boolean);
      conditions.forEach((condition, idx) => {
        const parsedDate = parseDate(condition);
        const displayDate = formatDateDisplay(parsedDate, locale);
        entries.push({
          date: displayDate.date,
          year: displayDate.year,
          title: condition.substring(0, 50) + (condition.length > 50 ? '...' : ''),
          description: condition,
          color: ['orange', 'yellow', 'blue', 'green', 'purple'][idx % 5] as TimelineEntry['color'],
          details: condition,
          sortDate: parsedDate?.getTime() || 0,
          confidence: medicalConfidence,
        });
      });
    }
  }

  // Parse surgeries and hospitalizations
  const surgeryField = Object.values(fields).find(f => f.field_name === 'SurgeriesAndHospitalizations');
  if (surgeryField?.value) {
    const surgeryConfidence = surgeryField.confidence;
    // Handle new format: array of objects
    if (Array.isArray(surgeryField.value)) {
      surgeryField.value.forEach((item: any) => {
        // Handle nested valueObject structure from Azure Content Understanding
        const surgery = item.valueObject || item;
        
        const procedure = getStringValue(surgery.procedure) || t('unknownProcedure');
        const date = getStringValue(surgery.date) || '';
        const reason = getStringValue(surgery.reason) || '';
        const outcome = getStringValue(surgery.outcome) || '';
        
        const title = `${procedure}${reason ? ' - ' + reason : ''}`;
        const details = `${procedure}\n${t('dateLabel')} ${date}\n${t('reasonLabel')} ${reason}\n${t('outcomeLabel')} ${outcome}`;
        
        const parsedDate = parseDate(date);
        const displayDate = formatDateDisplay(parsedDate, locale);
        
        entries.push({
          date: displayDate.date,
          year: displayDate.year,
          title: title.substring(0, 50) + (title.length > 50 ? '...' : ''),
          description: title,
          color: 'red',
          details: details,
          sortDate: parsedDate?.getTime() || 0,
          confidence: surgeryConfidence,
        });
      });
    } else {
      // Handle old format: semicolon-separated string
      const surgeries = String(surgeryField.value).split(';').map(s => s.trim()).filter(Boolean);
      surgeries.forEach((surgery) => {
        const parsedDate = parseDate(surgery);
        const displayDate = formatDateDisplay(parsedDate, locale);
        entries.push({
          date: displayDate.date,
          year: displayDate.year,
          title: surgery.substring(0, 50) + (surgery.length > 50 ? '...' : ''),
          description: surgery,
          color: 'red',
          details: surgery,
          sortDate: parsedDate?.getTime() || 0,
          confidence: surgeryConfidence,
        });
      });
    }
  }

  // Parse diagnostic tests
  const diagField = Object.values(fields).find(f => f.field_name === 'DiagnosticTestsSummary' || f.field_name === 'DiagnosticTests');
  if (diagField?.value) {
    const diagConfidence = diagField.confidence;
    // Handle new format: array of objects
    if (Array.isArray(diagField.value)) {
      diagField.value.forEach((item: any) => {
        // Handle nested valueObject structure from Azure Content Understanding
        const test = item.valueObject || item;
        
        const testType = getStringValue(test.testType) || t('unknownTest');
        const date = getStringValue(test.date) || '';
        const reason = getStringValue(test.reason) || '';
        const result = getStringValue(test.result) || '';
        
        const title = `${testType}${result ? ' - ' + result : ''}`;
        const details = `${testType}\n${t('dateLabel')} ${date}\n${t('reasonLabel')} ${reason}\n${t('resultLabel')} ${result}`;
        
        const parsedDate = parseDate(date);
        const displayDate = formatDateDisplay(parsedDate, locale);
        
        entries.push({
          date: displayDate.date,
          year: displayDate.year,
          title: title.substring(0, 50) + (title.length > 50 ? '...' : ''),
          description: title,
          color: 'purple',
          details: details,
          sortDate: parsedDate?.getTime() || 0,
          confidence: diagConfidence,
        });
      });
    } else {
      // Handle old format: semicolon-separated string
      const tests = String(diagField.value).split(';').map(s => s.trim()).filter(Boolean);
      tests.forEach((test) => {
        const parsedDate = parseDate(test);
        const displayDate = formatDateDisplay(parsedDate, locale);
        entries.push({
          date: displayDate.date,
          year: displayDate.year,
          title: test.substring(0, 50) + (test.length > 50 ? '...' : ''),
          description: test,
          color: 'purple',
          details: test,
          sortDate: parsedDate?.getTime() || 0,
          confidence: diagConfidence,
        });
      });
    }
  }

  // Sort entries by date in descending order (newest first)
  entries.sort((a, b) => (b.sortDate || 0) - (a.sortDate || 0));

  return entries;
}

function buildDocumentsFromData(application: ApplicationMetadata): { name: string; pages: number }[] {
  return (application.files || []).map(f => ({
    name: f.filename,
    pages: 1,
  }));
}

/**
 * Merge persisted action_history into timeline entries.
 */
function mergeActionHistory(entries: TimelineEntry[], application: ApplicationMetadata, locale: string, t: (key: string, values?: Record<string, string | number | Date>) => string): void {
  if (!application.action_history) return;
  for (const action of application.action_history) {
    const actionDate = new Date(action.at);
    const systems = (action.systems || []).filter((s: string) => s && !isWorkbenchSystem(s));
    const uniqueSystems = [...new Set(systems)];
    const badges = uniqueSystems.map((s: string) => {
      if (s === 'SIU') return '🔍 SIU';
      if (s === 'GED') return '📂 GED';
      if (s === 'Email') return '✉️ Email';
      return s;
    }).join(' · ');
    const d = formatDateDisplay(actionDate, locale);
    entries.push({
      date: d.date,
      year: d.year,
      title: action.label,
      description: badges ? t('systems', { systems: badges }) : action.source,
      color: action.performed === 'HITL' ? 'red' : 'green',
      details: badges ? `Action · ${badges}` : `Action · ${action.source}`,
      sortDate: actionDate.getTime(),
    });
  }
}

/**
 * Build timeline entries from LLM outputs generically — works for any persona.
 * Falls back to extracted fields timeline events if no LLM outputs.
 */
function buildGenericTimeline(application: ApplicationMetadata, locale: string, t: (key: string, values?: Record<string, string | number | Date>) => string, currency: CurrencyCode): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  const llm = application.llm_outputs || {};
  const fields = application.extracted_fields || {};
  const persona = application.persona || '';

  // For habitation/claims personas, build a coherent claims narrative
  if (persona.includes('habitation') || persona.includes('property')) {
    return buildHabitationTimeline(application, locale, t, currency);
  }

  // 1. Extract events from LLM outputs (any persona)
  for (const [section, subsections] of Object.entries(llm)) {
    if (!subsections || typeof subsections !== 'object') continue;
    for (const [subsection, output] of Object.entries(subsections as Record<string, any>)) {
      const parsed = output?.parsed;
      if (!parsed) continue;

      // Look for timeline_events arrays (clinical_timeline, treatment_timeline, etc.)
      const events = parsed.timeline_events || parsed.events || parsed.claim_lines;
      if (Array.isArray(events)) {
        events.forEach((evt: any, idx: number) => {
          const date = evt.date || evt.event_date || '';
          const title = evt.event || evt.description || evt.title
            || `${analysisSectionLabel(section, t)} — ${humanizeFieldKey(subsection)}`;
          const details = evt.description || evt.details || evt.rationale || '';
          const parsedDate = parseDate(date);
          const displayDate = formatDateDisplay(parsedDate, locale);
          entries.push({
            date: displayDate.date,
            year: displayDate.year,
            title: markdownPreview(String(title), 80),
            description: String(title),
            color: ['blue', 'green', 'orange', 'purple', 'yellow'][idx % 5] as TimelineEntry['color'],
            details: String(details),
            sortDate: parsedDate?.getTime() || 0,
          });
        });
      }

      // Extract summary as a single event if no timeline_events
      if (!Array.isArray(events) && parsed.summary) {
        const summary = String(parsed.summary);
        entries.push({
          date: '',
          year: '',
          title: t('aiAnalysis', { section: analysisSectionLabel(section, t) }),
          description: markdownPreview(summary, 80),
          color: 'blue',
          details: summary,
          sortDate: 0,
        });
      }
    }
  }

  // 2. If no LLM entries, build from date-like extracted fields only
  if (entries.length === 0) {
    for (const [key, val] of Object.entries(fields)) {
      if (!val || val.value == null || val.value === '') continue;
      const name = val.field_name || key.split(':').pop() || key;
      // Only include fields that contain actual dates
      if (!name.toLowerCase().includes('date')) continue;
      const parsedDate = parseDate(String(val.value));
      if (parsedDate) {
        const displayDate = formatDateDisplay(parsedDate, locale);
        entries.push({
          date: displayDate.date,
          year: displayDate.year,
          title: `${name}: ${String(val.value).substring(0, 60)}`,
          color: 'blue',
          details: `${name}: ${val.value}`,
          sortDate: parsedDate?.getTime() || 0,
          confidence: val.confidence,
        });
      }
    }
  }

  // Merge persisted action_history
  mergeActionHistory(entries, application, locale, t);

  // Sort chronologically (oldest first)
  entries.sort((a, b) => (b.sortDate || 0) - (a.sortDate || 0));
  return entries;
}


/**
 * Build a coherent claims timeline for habitation persona.
 * Creates narrative events from extracted fields with proper dates.
 */
function buildHabitationTimeline(application: ApplicationMetadata, locale: string, t: (key: string, values?: Record<string, string | number | Date>) => string, currency: CurrencyCode): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  const fields = application.extracted_fields || {};
  const llm = application.llm_outputs || {};

  // Helper to get field value
  const getVal = (names: string[]): string => {
    for (const name of names) {
      for (const [key, val] of Object.entries(fields)) {
        const fieldName = val?.field_name || key.split(':').pop() || key;
        if (fieldName === name && val?.value != null && val.value !== '') {
          return String(val.value);
        }
      }
    }
    return '';
  };

  const dateSinistre = getVal(['DateSinistre']);
  const natureSinistre = getVal(['NatureSinistre']);
  const description = getVal(['DescriptionSinistre']);
  const lieu = getVal(['LieuSinistre']);
  const montant = getVal(['MontantEstime']);
  const mesures = getVal(['MesuresConservatoires']);
  const nomAssure = getVal(['NomAssure', 'AssuréNom']);
  const contrat = getVal(['NumeroContrat']);
  const franchise = getVal(['FranchiseApplicable']);
  const tiers = getVal(['TiersImplique']);
  const urgence = getVal(['NiveauUrgence']);

  // Parse the incident date as base
  const incidentDate = parseDate(dateSinistre);
  const createdDate = application.created_at ? new Date(application.created_at) : new Date();

  // Build one-day-after, two-days-after from incident
  const dayAfter = incidentDate ? new Date(incidentDate.getTime() + 86400000) : null;
  const twoDaysAfter = incidentDate ? new Date(incidentDate.getTime() + 2 * 86400000) : null;

  // 1. Incident
  if (incidentDate && natureSinistre) {
    const d = formatDateDisplay(incidentDate, locale);
    entries.push({
      date: d.date, year: d.year,
      title: t('claimEventTitle', { nature: natureSinistre }),
      description: lieu ? t('claimEventLocation', { nature: natureSinistre, location: lieu }) : t('claimEvent', { nature: natureSinistre }),
      color: 'red',
      details: description || (lieu ? t('claimEventDetailsLocation', { nature: natureSinistre, date: dateSinistre, location: lieu }) : t('claimEventDetails', { nature: natureSinistre, date: dateSinistre })),
      sortDate: incidentDate.getTime(),
    });
  }

  // 2. Constatation des dégâts (day after incident)
  if (dayAfter && description) {
    const d = formatDateDisplay(dayAfter, locale);
    entries.push({
      date: d.date, year: d.year,
      title: t('damageObserved'),
      description: t('damageObservedBy', { name: nomAssure || t('insured') }),
      color: 'orange',
      details: description.substring(0, 300),
      sortDate: dayAfter.getTime(),
    });
  }

  // 3. Mesures conservatoires
  if (mesures) {
    const mesuresDate = dayAfter || incidentDate;
    if (mesuresDate) {
      const d = formatDateDisplay(mesuresDate, locale);
      entries.push({
        date: d.date, year: d.year,
        title: t('protectiveMeasures'),
        description: t('emergencyInterventions'),
        color: 'yellow',
        details: mesures,
        sortDate: mesuresDate.getTime() + 1,
      });
    }
  }

  // 4. Déclaration de sinistre (2 days after or creation date) 
  if (twoDaysAfter || createdDate) {
    const declDate = twoDaysAfter || createdDate;
    const d = formatDateDisplay(declDate, locale);
    entries.push({
      date: d.date, year: d.year,
      title: t('claimDeclaration'),
      description: contrat ? t('declarationSentContract', { contract: contrat }) : t('declarationSent'),
      color: 'blue',
      details: t('declarationDetails', { contract: contrat || '—', amount: montant || '—' }),
      sortDate: declDate.getTime(),
    });
  }

  // 5. Estimation des dommages
  if (montant) {
    const estimDate = twoDaysAfter || createdDate;
    const d = formatDateDisplay(estimDate, locale);
    const numMontant = Number(String(montant).replace(/[^\d.,]/g, '').replace(',', '.'));
    const montantDisplay = isNaN(numMontant)
      ? montant
      : formatAmount(numMontant, currency, locale);
    entries.push({
      date: d.date, year: d.year,
      title: t('damageEstimate', { amount: montantDisplay }),
      description: franchise ? t('damageEstimateDeductible', { deductible: franchise }) : t('damageEstimateTotal'),
      color: 'purple',
      details: t('damageEstimateDetails', { amount: montantDisplay, deductible: franchise || '—', thirdParty: tiers || '—' }),
      sortDate: (estimDate?.getTime() || 0) + 2,
    });
  }

  // 6. Upload / Réception du dossier (application creation date)
  {
    const d = formatDateDisplay(createdDate, locale);
    entries.push({
      date: d.date, year: d.year,
      title: t('fileReceived'),
      description: t('fileReceivedDescription', { brand: brand.name }),
      color: 'green',
      details: t('fileReceivedDetails', { date: createdDate.toLocaleDateString(locale), files: (application.files || []).map(f => f.filename).join(', ') }),
      sortDate: createdDate.getTime(),
    });
  }

  // 7. Urgence flag
  if (urgence && (urgence.toLowerCase().includes('elev') || urgence.toLowerCase().includes('élev') || urgence.toLowerCase().includes('critique'))) {
    entries.push({
      date: '', year: '',
      title: t('urgencyLevel', { level: urgence }),
      description: t('priorityFile'),
      color: 'red',
      details: t('urgencyDetails', { level: urgence }),
      sortDate: (incidentDate?.getTime() || createdDate.getTime()) - 1,
    });
  }

  // 8. Add LLM analysis results as events
  for (const [section, subsections] of Object.entries(llm)) {
    if (!subsections || typeof subsections !== 'object') continue;
    for (const [, output] of Object.entries(subsections as Record<string, any>)) {
      const parsed = output?.parsed;
      if (!parsed?.summary) continue;
      const summary = String(parsed.summary);
      const d = formatDateDisplay(createdDate, locale);
      entries.push({
        date: d.date, year: d.year,
        title: t('aiAnalysis', { section: analysisSectionLabel(section, t) }),
        description: markdownPreview(summary, 80),
        color: 'green',
        details: summary,
        sortDate: createdDate.getTime() + 10,
      });
    }
  }

  // Merge persisted action_history
  mergeActionHistory(entries, application, locale, t);

  // Sort chronologically (oldest first)
  entries.sort((a, b) => (a.sortDate || 0) - (b.sortDate || 0));
  return entries;
}

/** Labels for persona context */
function getPersonaLabels(persona: string | undefined, t: (key: string) => string) {
  const isHabitation = persona?.includes('habitation') || persona?.includes('property');
  const isClaims = persona?.includes('claims') || persona?.includes('sinistre');
  const isMortgage = persona?.includes('mortgage') || persona?.includes('hypothe');

  if (isHabitation) return {
    title: t('claimsTitle'),
    subtitle: t('habitationSubtitle'),
    itemsTab: t('eventsTab'),
    docsTab: t('documentsTab'),
    emptyItems: t('noEvents'),
    emptyDocs: t('noDocuments'),
  };
  if (isClaims) return {
    title: t('claimsTitle'),
    subtitle: t('claimsSubtitle'),
    itemsTab: t('eventsTab'),
    docsTab: t('documentsTab'),
    emptyItems: t('noEvents'),
    emptyDocs: t('noDocuments'),
  };
  if (isMortgage) return {
    title: t('mortgageTitle'),
    subtitle: t('mortgageSubtitle'),
    itemsTab: t('stepsTab'),
    docsTab: t('documentsTab'),
    emptyItems: t('noSteps'),
    emptyDocs: t('noDocuments'),
  };
  // Default: underwriting / medical
  return {
    title: t('defaultTitle'),
    subtitle: t('defaultSubtitle'),
    itemsTab: t('medicalEventsTab'),
    docsTab: t('documentsTab'),
    emptyItems: t('noMedicalEvents'),
    emptyDocs: t('noDocuments'),
  };
}

export default function ChronologicalOverview({ application, fullWidth, persona }: ChronologicalOverviewProps) {
  const [activeTab, setActiveTab] = useState<'items' | 'documents'>('items');
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());
  const t = useTranslations('chronological');
  const locale = useLocale();
  const currency = useApplicationCurrency(application);

  const labels = getPersonaLabels(persona || application.persona, t);
  const isMedicalPersona = !persona?.includes('habitation') && !persona?.includes('property') && !persona?.includes('mortgage') &&
    !application.persona?.includes('habitation') && !application.persona?.includes('property') && !application.persona?.includes('mortgage');

  // Use medical-specific builder for underwriting, generic for everything else
  const timelineItems = isMedicalPersona
    ? buildTimelineFromData(application, locale, t)
    : buildGenericTimeline(application, locale, t, currency);
  const documents = buildDocumentsFromData(application);

  const colorClasses: Record<string, string> = {
    orange: 'bg-orange-500',
    yellow: 'bg-yellow-500',
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    purple: 'bg-purple-500',
    red: 'bg-red-500',
  };

  const toggleExpand = (idx: number) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(idx)) {
      newExpanded.delete(idx);
    } else {
      newExpanded.add(idx);
    }
    setExpandedItems(newExpanded);
  };

  return (
    <div className={clsx(
      "bg-white rounded-xl shadow-sm border border-slate-200 h-full min-h-0 flex flex-col",
      !fullWidth && "max-w-4xl"
    )}>
      {/* Header */}
      <div className="p-4 border-b border-slate-200">
        <h2 className="text-lg font-semibold text-slate-900">{labels.title}</h2>
        <p className="text-xs text-slate-500 mt-1">
          {labels.subtitle}
        </p>

        {/* Tabs */}
        <div className="flex mt-3 border-b border-slate-200">
          <button
            onClick={() => setActiveTab('items')}
            className={clsx(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === 'items'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            )}
          >
            {labels.itemsTab} ({timelineItems.length})
          </button>
          <button
            onClick={() => setActiveTab('documents')}
            className={clsx(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === 'documents'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            )}
          >
            {labels.docsTab} ({documents.length})
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-auto p-4">
        {activeTab === 'items' ? (
          timelineItems.length > 0 ? (
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-8 top-0 bottom-0 w-px bg-slate-200" />

              {/* Timeline items */}
              <div className="space-y-4">
                {timelineItems.map((item, idx) => (
                  <div key={idx} className="relative flex gap-4">
                    {/* Date column */}
                    <div className="w-12 text-right flex-shrink-0">
                      <div className="text-xs font-medium text-slate-500">{item.date}</div>
                      <div className="text-xs text-slate-400">{item.year}</div>
                    </div>

                    {/* Timeline dot */}
                    <div
                      className={clsx(
                        'w-3 h-3 rounded-full flex-shrink-0 mt-1 z-10',
                        colorClasses[item.color]
                      )}
                    />

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <button
                        onClick={() => toggleExpand(idx)}
                        className="flex items-center justify-between w-full text-left group"
                      >
                        <div className="flex items-center gap-2">
                          <div className="text-sm font-medium text-slate-900 group-hover:text-blue-600 transition-colors">
                            {item.title}
                          </div>
                          {item.confidence !== undefined && (
                            <ConfidenceIndicator 
                              confidence={item.confidence} 
                              fieldName={item.title}
                            />
                          )}
                        </div>
                        {item.details && (
                          expandedItems.has(idx) ? (
                            <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
                          )
                        )}
                      </button>

                      {/* Expanded content (AI text may be Markdown) */}
                      {expandedItems.has(idx) && item.details && (
                        <div className="mt-2 rounded-lg bg-slate-50 p-3">
                          <MarkdownText>{item.details}</MarkdownText>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500 italic text-center py-8">
              {labels.emptyItems}
            </p>
          )
        ) : (
          // Documents tab
          documents.length > 0 ? (
            <div className="space-y-2">
              {documents.map((doc, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg"
                >
                  <FileText className="w-5 h-5 text-blue-500" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">
                      {doc.name}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500 italic text-center py-8">
              {labels.emptyDocs}
            </p>
          )
        )}
      </div>
    </div>
  );
}
