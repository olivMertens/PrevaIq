'use client';

import { useMemo } from 'react';
import { ChevronRight, CircleCheck, CircleX, ExternalLink, FileText, TriangleAlert, Umbrella } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { formatAmount, parseAmount, type CurrencyCode } from '@/lib/currency';
import type { ContextLabel } from '@/lib/types';
import MarkdownText from './MarkdownText';
import { ANALYSIS_SEPARATOR } from './analysisMarkdown';
import { CoverageAmounts, CoverageVerdict, SECTION_TITLE } from './CoverageSummary';
import { CoverageList, CoverageRules, GuaranteeList, PolicyArticles, TextList } from './CoverageSections';
import { buildCoverageView, coverageOutputs, sortByTone } from './coverageView';
import { formatParsedFields } from './propertyClaimHelpers';

interface CoverTabProps {
  labels: ContextLabel[];
  llmOutputs: Record<string, unknown>;
  /** Labels of field names and coded values translated with the analysis. */
  analysisLabels?: Record<string, string>;
  currency: CurrencyCode;
  /** Claimed amount as written in the claim. */
  claimedText: string;
  deductibleText?: string;
  /** AI text about cover and decision, shown when the case has no structured coverage analysis. */
  coverageText: string;
}

/** Backend labels carry their own ✓/✗ glyph; the cockpit shows a real icon instead. */
export function cleanLabel(label: string): string {
  return String(label).replace(/^[\s✓✔✗✘×]+/u, '').trim();
}

function LabelRow({ label }: { label: ContextLabel }) {
  const status = label.urgency === 'success' ? 'ok' : label.urgency === 'critical' ? 'critical' : label.type === 'guarantee' ? 'neutral' : 'warning';
  const Icon = { ok: CircleCheck, critical: CircleX, warning: TriangleAlert, neutral: Umbrella }[status];
  const color = { ok: 'text-emerald-700', critical: 'text-rose-700', warning: 'text-amber-700', neutral: 'text-slate-500' }[status];
  let host = '';
  if (label.source_url) {
    try { host = new URL(label.source_url).hostname.replace(/^www\./, ''); } catch { host = ''; }
  }
  return (
    <li className="flex gap-3 rounded-lg border border-slate-200 p-3">
      <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${color}`} aria-hidden />
      <div className="min-w-0">
        <p className="font-medium text-slate-900">{cleanLabel(label.label)}</p>
        {typeof label.tooltip === 'string' && label.tooltip && <p className="text-slate-600">{label.tooltip}</p>}
        {host && (
          <a href={label.source_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-indigo-700 hover:underline">
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            {host}
          </a>
        )}
      </div>
    </li>
  );
}

function LabelSection({ title, labels }: { title: string; labels: ContextLabel[] }) {
  if (labels.length === 0) return null;
  return (
    <section>
      <h3 className={SECTION_TITLE}>{title}</h3>
      <ul className="space-y-2">{labels.map((label) => <LabelRow key={label.key} label={label} />)}</ul>
    </section>
  );
}

/**
 * Cover & amounts: the coverage verdict and the indemnity first, then the claim items,
 * guarantees, exclusions and rules applied; policy articles and the full analysis on demand.
 */
export default function CoverTab({ labels, llmOutputs, analysisLabels, currency, claimedText, deductibleText, coverageText }: CoverTabProps) {
  const t = useTranslations('caseCockpit.coverTab');
  const tClaims = useTranslations('claims');
  const locale = useLocale();
  const money = (value: number) => formatAmount(value, currency, locale, { maximumFractionDigits: 0 });
  const { coverage, settlement } = useMemo(() => coverageOutputs(llmOutputs), [llmOutputs]);
  const view = useMemo(() => buildCoverageView(coverage, settlement), [coverage, settlement]);
  const fullAnalysis = useMemo(
    () => [coverage, settlement]
      .flatMap((parsed) => (parsed ? [formatParsedFields(parsed, tClaims, locale, currency, analysisLabels).join('\n')] : []))
      .filter(Boolean)
      .join(ANALYSIS_SEPARATOR),
    [coverage, settlement, tClaims, locale, currency, analysisLabels],
  );
  const claimedValue = parseAmount(claimedText);
  const claimed = Number.isFinite(claimedValue) && claimedValue > 0 ? claimedValue : undefined;
  const checks = labels.filter((label) => label.type === 'verification' || label.type === 'alert');
  const guaranteeLabels = labels.filter((label) => label.type === 'guarantee');

  if (!view.hasContent) {
    return (
      <div className="space-y-5 text-sm">
        <CoverageAmounts view={view} claimed={claimed} claimedText={claimedText} deductibleText={deductibleText} money={money} />
        <LabelSection title={t('checks')} labels={checks} />
        <LabelSection title={t('guarantees')} labels={guaranteeLabels} />
        <section>
          <h3 className={SECTION_TITLE}>{t('aiCoverage')}</h3>
          {coverageText ? <MarkdownText>{coverageText}</MarkdownText> : <p className="text-slate-500">{t('noCoverage')}</p>}
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-5 text-sm">
      <CoverageVerdict view={view} claimed={claimed} money={money} />
      <CoverageAmounts view={view} claimed={claimed} claimedText={claimedText} deductibleText={deductibleText} money={money} />
      <CoverageList title={t('items', { count: view.lines.length })} entries={sortByTone(view.lines)} money={money} />
      {view.guarantees.length > 0
        ? <GuaranteeList guarantees={view.guarantees} />
        : <LabelSection title={t('guarantees')} labels={guaranteeLabels} />}
      <CoverageList title={t('exclusions')} intro={view.exclusionsSummary} entries={view.exclusions} attention={view.attention} />
      <CoverageRules rules={view.rules} money={money} />
      <LabelSection title={t('checks')} labels={checks} />
      <TextList title={t('basis')} items={view.basis} />
      <TextList title={t('conditions')} items={view.conditions} />
      <PolicyArticles articles={view.articles} citations={view.citations} />
      {fullAnalysis && (
        <details className="group rounded-lg border border-slate-200">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 font-medium text-slate-800 [&::-webkit-details-marker]:hidden">
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-slate-400 transition-transform group-open:rotate-90" aria-hidden />
            <FileText className="h-4 w-4 flex-shrink-0 text-slate-500" aria-hidden />
            {t('fullAnalysis')}
          </summary>
          <div className="border-t border-slate-200 p-3">
            <MarkdownText>{fullAnalysis}</MarkdownText>
          </div>
        </details>
      )}
    </div>
  );
}
