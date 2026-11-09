'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { ChevronDown, ChevronUp, FileText } from 'lucide-react';
import type { ApplicationMetadata } from '@/lib/types';
import { useApplicationCurrency } from '@/lib/CurrencyProvider';
import { buildTimelineFromData, buildDocumentsFromData, buildGenericTimeline } from './chronology/buildTimeline';
import MarkdownText from './claims/property/MarkdownText';
import ConfidenceIndicator from './ConfidenceIndicator';
import clsx from 'clsx';

interface ChronologicalOverviewProps {
  application: ApplicationMetadata;
  fullWidth?: boolean;
  persona?: string;
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
  const tSubject = useTranslations('claimSubjects');
  const locale = useLocale();
  const currency = useApplicationCurrency(application);

  const labels = getPersonaLabels(persona || application.persona, t);
  const isMedicalPersona = !persona?.includes('habitation') && !persona?.includes('property') && !persona?.includes('mortgage') &&
    !application.persona?.includes('habitation') && !application.persona?.includes('property') && !application.persona?.includes('mortgage');

  // Use medical-specific builder for underwriting, generic for everything else
  const timelineItems = isMedicalPersona
    ? buildTimelineFromData(application, locale, t)
    : buildGenericTimeline(application, locale, t, currency, tSubject);
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
