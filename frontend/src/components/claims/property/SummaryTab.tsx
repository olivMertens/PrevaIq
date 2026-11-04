'use client';

import { useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';
import ChronologicalOverview from '../../ChronologicalOverview';
import MarkdownText from './MarkdownText';
import { parseAiSummary } from './propertyClaimHelpers';

type SummaryTabKey = 'overview' | 'damages' | 'decision' | 'risk' | 'timeline' | 'raw';

interface DamageRow {
  label: string;
  related: string;
}

interface SummaryTabProps {
  application: ApplicationMetadata;
  aiSummary: string;
  damages: DamageRow[];
  analyzing: boolean;
  onRelaunch: () => void;
}

/** Full AI synthesis, split by topic (moved from the former "AI summary" dialog). */
export default function SummaryTab({ application, aiSummary, damages, analyzing, onRelaunch }: SummaryTabProps) {
  const t = useTranslations('claims');
  const [tab, setTab] = useState<SummaryTabKey>('overview');
  const parsed = parseAiSummary(aiSummary || '');
  const tabs: Array<{ key: SummaryTabKey; label: string }> = [
    { key: 'overview', label: t('analysis.tabOverview') },
    { key: 'damages', label: t('analysis.tabDamages') },
    { key: 'decision', label: t('analysis.tabDecision') },
    { key: 'risk', label: t('analysis.tabRisk') },
    { key: 'timeline', label: t('analysis.tabTimeline') },
    { key: 'raw', label: t('analysis.tabRaw') },
  ];
  const empty = <p className="text-sm italic text-slate-500">{t('analysis.noContent')}</p>;

  const content = () => {
    if (tab === 'raw') return aiSummary ? <MarkdownText>{aiSummary}</MarkdownText> : empty;
    if (tab === 'timeline') return <ChronologicalOverview application={application} fullWidth />;
    if (tab === 'damages') {
      if (damages.length > 0) {
        return (
          <table className="w-full border-collapse overflow-hidden rounded-lg bg-white text-sm">
            <thead>
              <tr className="bg-slate-100">
                <th className="border-b p-3 text-left font-medium text-slate-700">{t('documents.zoneDamageFull')}</th>
                <th className="w-32 border-b p-3 text-left font-medium text-slate-700">{t('damage.relatedToClaim')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {damages.map((row, index) => (
                <tr key={index}>
                  <td className="p-3 text-slate-900">{row.label}</td>
                  <td className="p-3"><span className="rounded bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-800">{row.related}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        );
      }
      return parsed.damages ? <MarkdownText>{parsed.damages}</MarkdownText> : empty;
    }
    return parsed[tab] ? <MarkdownText>{parsed[tab]}</MarkdownText> : empty;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div role="group" aria-label={t('panels.aiSummary')} className="flex flex-wrap gap-1">
          {tabs.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={tab === item.key}
              onClick={() => setTab(item.key)}
              className={clsx(
                'rounded-lg px-3 py-1.5 text-sm',
                tab === item.key ? 'bg-indigo-50 font-medium text-indigo-700' : 'text-slate-600 hover:bg-slate-100',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onRelaunch}
          disabled={analyzing}
          className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-60"
        >
          {analyzing ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="h-4 w-4" aria-hidden />}
          {analyzing ? t('analysis.inProgress') : t('analysis.relaunch')}
        </button>
      </div>
      <div className="min-h-[200px] rounded-lg bg-slate-50 p-4">{aiSummary || tab === 'timeline' ? content() : empty}</div>
    </div>
  );
}
