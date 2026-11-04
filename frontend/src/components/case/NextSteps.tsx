'use client';

import { useMemo } from 'react';
import { FileDown, Lock, Mail } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import { CockpitCard } from './caseUi';

export interface StepItem {
  key: string;
  task: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  dueOffsetDays: number;
}

export type SettlementState = 'ready' | 'blocked' | 'locked';

interface NextStepsProps {
  steps: StepItem[];
  checked: number[];
  onToggle: (index: number) => void;
  recommendedKey?: string;
  /** Steps that come with a ready-made customer message. */
  draftKeys?: string[];
  onDraftMessage: () => void;
  settlement: SettlementState;
  onGenerateSettlement: () => void;
}

const PRIORITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 } as const;

/** One checklist: recommended step first, a message draft where it helps, settlement last. */
export default function NextSteps({
  steps,
  checked,
  onToggle,
  recommendedKey,
  draftKeys = [],
  onDraftMessage,
  settlement,
  onGenerateSettlement,
}: NextStepsProps) {
  const t = useTranslations('caseCockpit.steps');
  const ordered = useMemo(
    () =>
      steps
        .map((step, index) => ({ step, index }))
        .sort(
          (a, b) =>
            Number(b.step.key === recommendedKey) - Number(a.step.key === recommendedKey) ||
            PRIORITY_RANK[a.step.priority] - PRIORITY_RANK[b.step.priority] ||
            a.step.dueOffsetDays - b.step.dueOffsetDays,
        ),
    [steps, recommendedKey],
  );
  const done = checked.filter((index) => index < steps.length).length;
  const dueLabel = (days: number) =>
    days <= 0 ? t('due.today') : days === 1 ? t('due.tomorrow') : t('due.inDays', { days });

  return (
    <CockpitCard
      title={t('title')}
      headingId="cockpit-steps"
      aside={<span className="text-sm text-slate-600">{t('progress', { done, total: steps.length })}</span>}
    >
      <div className="px-4 pt-3">
        <div
          className="h-1.5 rounded-full bg-slate-100"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={done}
          aria-label={t('progress', { done, total: steps.length })}
        >
          <div
            className="h-1.5 rounded-full bg-indigo-600 transition-all"
            style={{ width: `${steps.length ? Math.max(4, (done / steps.length) * 100) : 0}%` }}
          />
        </div>
      </div>
      {steps.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate-500">{t('empty')}</p>
      ) : (
        <ul className="space-y-1 p-2 text-sm">
          {ordered.map(({ step, index }) => {
            const isChecked = checked.includes(index);
            const recommended = step.key === recommendedKey;
            return (
              <li
                key={`${step.key}-${index}`}
                className={clsx(
                  'flex items-center gap-3 rounded-lg p-2',
                  recommended && !isChecked && 'border border-rose-200 bg-rose-50',
                )}
              >
                <input
                  id={`step-${index}`}
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => onToggle(index)}
                  className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                />
                <label htmlFor={`step-${index}`} className="min-w-0 flex-1 cursor-pointer">
                  <span className={clsx('block font-medium', isChecked ? 'text-slate-400 line-through' : 'text-slate-900')}>
                    {step.task}
                  </span>
                  <span className={clsx('block text-xs', recommended && !isChecked ? 'text-rose-700' : 'text-slate-500')}>
                    {recommended ? `${t('recommended')} · ` : ''}
                    {dueLabel(step.dueOffsetDays)}
                  </span>
                </label>
                {draftKeys.includes(step.key) && !isChecked && (
                  <button
                    type="button"
                    onClick={onDraftMessage}
                    className="inline-flex flex-shrink-0 items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Mail className="h-3.5 w-3.5" aria-hidden />
                    {t('draft')}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <div className="border-t border-slate-100 p-2">
        {settlement === 'ready' ? (
          <button
            type="button"
            onClick={onGenerateSettlement}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <FileDown className="h-4 w-4" aria-hidden />
            {t('settlement')}
          </button>
        ) : (
          <p className="flex items-center gap-2 p-2 text-sm text-slate-500">
            <Lock className="h-4 w-4 flex-shrink-0" aria-hidden />
            {t('settlement')} · {settlement === 'blocked' ? t('settlementBlocked') : t('settlementLocked')}
          </p>
        )}
      </div>
    </CockpitCard>
  );
}
