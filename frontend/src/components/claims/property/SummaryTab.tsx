'use client';

import { Loader2, RefreshCw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import MarkdownText from './MarkdownText';
import { parseAiSummary } from './propertyClaimHelpers';

type SummaryTabKey = 'overview' | 'damages' | 'decision' | 'risk' | 'raw';

interface DamageRow {
  label: string;
  related: string;
}

interface SummaryTabProps {
  aiSummary: string;
  damages: DamageRow[];
  analyzing: boolean;
  onRelaunch: () => void;
}

/** Full AI synthesis, split by topic (moved from the former "AI summary" dialog). */
export default function SummaryTab({ aiSummary, damages, analyzing, onRelaunch }: SummaryTabProps) {
  const t = useTranslations('claims');
  const parsed = parseAiSummary(aiSummary || '');
  const tabs: Array<{ key: SummaryTabKey; label: string }> = [
    { key: 'overview', label: t('analysis.tabOverview') },
    { key: 'damages', label: t('analysis.tabDamages') },
    { key: 'decision', label: t('analysis.tabDecision') },
    { key: 'risk', label: t('analysis.tabRisk') },
    { key: 'raw', label: t('analysis.tabRaw') },
  ];
  const empty = <p className="text-sm italic text-slate-500">{t('analysis.noContent')}</p>;

  const content = (tab: SummaryTabKey) => {
    if (tab === 'raw') return aiSummary ? <MarkdownText>{aiSummary}</MarkdownText> : empty;
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
        <p className="text-sm text-slate-600">{t('panels.aiSummary')}</p>
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
      {tabs.map(({ key, label }) => (
        <details key={key} open={key === 'overview'} className="rounded-lg border border-slate-200 bg-slate-50">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-slate-800">{label}</summary>
          <div className="px-4 pb-4">{content(key)}</div>
        </details>
      ))}
    </div>
  );
}
