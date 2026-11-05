'use client';

import clsx from 'clsx';
import { BookOpen, ChevronRight, CircleMinus, TriangleAlert } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import type { ReactNode } from 'react';
import { humanizeCode, isCode, type CoverageArticle, type CoverageCitation, type CoverageEntry, type CoverageRule, type CoverageTone, type CoverageView } from './coverageView';
import { TONE_STYLE } from './coverageTone';
import { SECTION_TITLE } from './CoverageSummary';

type Money = (value: number) => string;

const SUMMARY_ROW = 'flex cursor-pointer list-none items-center gap-2 [&::-webkit-details-marker]:hidden';

export function ToneChip({ tone, children }: { tone: CoverageTone; children: ReactNode }) {
  return (
    <span className={clsx('inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset', TONE_STYLE[tone].chip)}>
      {children}
    </span>
  );
}

function References({ references }: { references: string[] }) {
  if (references.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {references.map((reference) => (
        <span key={reference} className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
          <BookOpen className="h-3 w-3" aria-hidden />
          {reference}
        </span>
      ))}
    </div>
  );
}

function useEntryName() {
  const t = useTranslations('caseCockpit.coverTab');
  return (entry: CoverageEntry) => (entry.peril ? t(`perils.${entry.peril}`) : entry.name);
}

function EntryRow({ entry, money }: { entry: CoverageEntry; money?: Money }) {
  const t = useTranslations('caseCockpit.coverTab');
  const name = useEntryName();
  const style = TONE_STYLE[entry.tone];
  return (
    <li className="flex gap-3 rounded-lg border border-slate-200 p-3">
      <style.Icon className={clsx('mt-0.5 h-4 w-4 flex-shrink-0', style.icon)} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <p className="min-w-0 font-medium text-slate-900">{name(entry)}</p>
          <div className="ml-auto flex flex-shrink-0 items-center gap-2">
            {entry.amount !== undefined && money && <span className="font-semibold tabular-nums text-slate-900">{money(entry.amount)}</span>}
            {entry.tone !== 'unknown' && <ToneChip tone={entry.tone}>{t(`tone.${entry.tone}`)}</ToneChip>}
          </div>
        </div>
        {entry.reason && <p className="mt-1 text-slate-600">{entry.reason}</p>}
        {entry.notes.length > 0 && (
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-slate-600">
            {entry.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        )}
        <References references={entry.references} />
      </div>
    </li>
  );
}

interface CoverageListProps {
  title: string;
  entries: CoverageEntry[];
  money?: Money;
  /** One-sentence conclusion of the analysis for this list. */
  intro?: string;
  /** Points of attention without a status of their own. */
  attention?: string[];
}

/** Claim items or exclusions, one card per entry with its status, amount and reason. */
export function CoverageList({ title, entries, money, intro, attention = [] }: CoverageListProps) {
  if (entries.length === 0 && attention.length === 0 && !intro) return null;
  return (
    <section>
      <h3 className={SECTION_TITLE}>{title}</h3>
      {intro && <p className="mb-2 text-slate-700">{intro}</p>}
      <ul className="space-y-2">
        {entries.map((entry, index) => <EntryRow key={`${entry.name}-${index}`} entry={entry} money={money} />)}
        {attention.map((point) => (
          <li key={point} className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50/60 p-3">
            <TriangleAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" aria-hidden />
            <p className="text-slate-800">{point}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Guarantees involved in the claim; the perils not involved fold into one line. */
export function GuaranteeList({ guarantees }: { guarantees: CoverageEntry[] }) {
  const t = useTranslations('caseCockpit.coverTab');
  const name = useEntryName();
  if (guarantees.length === 0) return null;
  const involved = guarantees.filter((entry) => entry.tone !== 'notConcerned');
  const others = guarantees.filter((entry) => entry.tone === 'notConcerned');
  return (
    <section>
      <h3 className={SECTION_TITLE}>{t('guarantees')}</h3>
      {involved.length > 0 && (
        <ul className="space-y-2">
          {involved.map((entry, index) => <EntryRow key={`${entry.name}-${index}`} entry={entry} />)}
        </ul>
      )}
      {others.length > 0 && (
        <details className="group mt-2 rounded-lg border border-slate-200 px-3 py-2 text-slate-600">
          <summary className={SUMMARY_ROW}>
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-slate-400 transition-transform group-open:rotate-90" aria-hidden />
            <CircleMinus className="h-4 w-4 flex-shrink-0 text-slate-400" aria-hidden />
            <span>{t('notInvolved', { perils: others.map(name).join(' · ') })}</span>
          </summary>
          <ul className="mt-2 space-y-1 pl-6">
            {others.map((entry, index) => (
              <li key={`${entry.name}-${index}`}>
                <span className="font-medium text-slate-700">{name(entry)}</span>
                {entry.reason && <span> — {entry.reason}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

type RuleKey = keyof CoverageView['rules'];

const RULE_ANSWERS: Record<Exclude<RuleKey, 'deductible'>, [string, string]> = {
  catNat: ['applies', 'notApplicable'],
  irsi: ['applies', 'notApplicable'],
  expertise: ['required', 'notRequired'],
  recourse: ['possible', 'notPossible'],
};

/** Deductible, Cat-Nat, IRSI, expert appraisal and recourse: the answer, then why. */
export function CoverageRules({ rules, money }: { rules: CoverageView['rules']; money: Money }) {
  const t = useTranslations('caseCockpit.coverTab');
  const locale = useLocale();
  // Recourse targets written as English codes are only readable in an English UI.
  const targets = (against: string[] = []) =>
    against.filter((item) => locale.startsWith('en') || !isCode(item)).map(humanizeCode);
  const rows = (['deductible', 'catNat', 'irsi', 'expertise', 'recourse'] as const).flatMap((key) => {
    const rule: (CoverageRule & { against?: string[] }) | undefined = rules[key];
    return rule ? [{ key, rule }] : [];
  });
  if (rows.length === 0) return null;

  const answer = (key: RuleKey, rule: CoverageRule) => {
    if (key === 'deductible') {
      if (rule.amount !== undefined) return money(rule.amount);
      if (rule.detail) return rule.detail;
      return t(`ruleValue.${rule.applies === null ? 'unknown' : rule.applies ? 'applies' : 'notApplicable'}`);
    }
    const [yes, no] = RULE_ANSWERS[key];
    return t(`ruleValue.${rule.applies === null ? 'unknown' : rule.applies ? yes : no}`);
  };
  // Answers that call for an action stand out: an appraisal to order, a recourse to start.
  const emphasis = (key: RuleKey, rule: CoverageRule) =>
    rule.applies && key === 'expertise' ? 'text-amber-800' : rule.applies && key === 'recourse' ? 'text-emerald-800' : 'text-slate-900';

  return (
    <section>
      <h3 className={SECTION_TITLE}>{t('rules')}</h3>
      <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200">
        {rows.map(({ key, rule }) => (
          <div key={key} className="grid gap-x-4 gap-y-0.5 p-3 sm:grid-cols-[9rem_minmax(0,1fr)]">
            <dt className="text-slate-500">{t(`rule.${key}`)}</dt>
            <dd className="min-w-0">
              <p className={clsx('font-medium', emphasis(key, rule))}>{answer(key, rule)}</p>
              {rule.detail && (key !== 'deductible' || rule.amount !== undefined) && <p className="text-xs text-slate-500">{rule.detail}</p>}
              {targets(rule.against).length > 0 && <p className="text-slate-700">{t('recourseAgainst', { targets: targets(rule.against).join(' · ') })}</p>}
              {rule.reason && <p className="mt-0.5 text-slate-600">{rule.reason}</p>}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function TextList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h3 className={SECTION_TITLE}>{title}</h3>
      <ul className="list-disc space-y-1 pl-5 text-slate-700">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </section>
  );
}

function CitationCard({ citation }: { citation: CoverageCitation }) {
  const t = useTranslations('caseCockpit.coverTab');
  const quoted = citation.name || citation.condition || citation.effect;
  return (
    <li className="rounded-md border border-slate-200 p-3">
      <p className="flex flex-wrap items-baseline gap-x-2 font-medium text-slate-900">
        {citation.reference}
        {citation.id && citation.id !== citation.reference && <span className="font-mono text-xs font-normal text-slate-400">{citation.id}</span>}
      </p>
      {citation.why && <p className="mt-1 text-slate-700">{citation.why}</p>}
      {quoted && (
        <div className="mt-2 space-y-1 border-l-2 border-slate-200 pl-3 text-xs text-slate-600">
          <p className="font-semibold uppercase tracking-wide text-slate-400">{t('citation.wording')}</p>
          {citation.name && <p className="italic">{citation.name}</p>}
          {citation.condition && (
            <p>
              <span className="font-medium text-slate-700">{t('citation.condition')}</span> {citation.condition}
            </p>
          )}
          {citation.effect && (
            <p>
              <span className="font-medium text-slate-700">{t('citation.effect')}</span> {citation.effect}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

/**
 * Policy articles behind the assessment, folded by default: the analysis explains each one in
 * the UI language; the quoted wording stays in the language of the policy.
 */
export function PolicyArticles({ articles, citations }: { articles: CoverageArticle[]; citations: CoverageCitation[] }) {
  const t = useTranslations('caseCockpit.coverTab');
  if (articles.length === 0 && citations.length === 0) return null;
  const listed = articles.filter((article) => !article.status && !article.effect);
  const described = articles.filter((article) => article.status || article.effect);
  return (
    <details className="group rounded-lg border border-slate-200">
      <summary className={clsx(SUMMARY_ROW, 'px-3 py-2.5 font-medium text-slate-800')}>
        <ChevronRight className="h-4 w-4 flex-shrink-0 text-slate-400 transition-transform group-open:rotate-90" aria-hidden />
        <BookOpen className="h-4 w-4 flex-shrink-0 text-slate-500" aria-hidden />
        {t('articles', { count: citations.length > 0 ? citations.length : articles.length })}
      </summary>
      <div className="space-y-3 border-t border-slate-200 p-3">
        {listed.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {listed.map((article) => (
              <li key={article.reference} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">{article.reference}</li>
            ))}
          </ul>
        )}
        {described.length > 0 && (
          <ul className="space-y-2">
            {described.map((article) => (
              <li key={article.reference} className="rounded-md border border-slate-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-slate-900">{article.reference}</p>
                  {article.status && <ToneChip tone={article.tone}>{article.status}</ToneChip>}
                </div>
                {article.effect && <p className="mt-1 text-slate-600">{article.effect}</p>}
              </li>
            ))}
          </ul>
        )}
        {citations.length > 0 && (
          <ul className="space-y-2">
            {citations.map((citation) => <CitationCard key={citation.id ?? `${citation.reference}-${citation.condition}`} citation={citation} />)}
          </ul>
        )}
      </div>
    </details>
  );
}
