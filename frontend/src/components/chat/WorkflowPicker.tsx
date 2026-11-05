'use client';

import clsx from 'clsx';
import { Layers, ShieldAlert, Sparkles, Zap } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ChatMode, ChatRecommendation } from './types';

const WORKFLOWS = [
  {
    id: 'fraude',
    nameKey: 'workflowFraudName',
    patternKey: 'workflowFraudPattern',
    durationKey: 'workflowFraudDuration',
    icon: ShieldAlert,
    iconClass: 'bg-rose-50 text-rose-600',
    highlightClass: 'border-rose-300 bg-rose-50/70 ring-1 ring-rose-200',
  },
  {
    id: 'complet',
    nameKey: 'workflowCompleteName',
    patternKey: 'workflowCompletePattern',
    durationKey: 'workflowCompleteDuration',
    icon: Layers,
    iconClass: 'bg-indigo-50 text-indigo-600',
    highlightClass: 'border-indigo-300 bg-indigo-50/70 ring-1 ring-indigo-200',
  },
  {
    id: 'express',
    nameKey: 'workflowExpressName',
    patternKey: 'workflowExpressPattern',
    durationKey: 'workflowExpressDuration',
    icon: Zap,
    iconClass: 'bg-emerald-50 text-emerald-600',
    highlightClass: 'border-emerald-300 bg-emerald-50/70 ring-1 ring-emerald-200',
  },
] as const;

const MODE_LABEL_KEYS: Record<ChatMode, string> = {
  auto: 'agentAuto',
  data: 'agentData',
  policy: 'agentPolicy',
  analysis: 'agentAnalysis',
  dashboard: 'agentDashboard',
  workflow: 'agentWorkflow',
};

/** Best-scored workflow recommendation (recommendations are sorted by score). */
function topWorkflow(recommendations: ChatRecommendation[]) {
  for (const recommendation of recommendations) {
    const workflow = WORKFLOWS.find((item) => item.id === recommendation.id);
    if (workflow) return { workflow, reason: recommendation.reason };
  }
  return null;
}

interface WorkflowPickerProps {
  recommendations: ChatRecommendation[];
  /** Workflows need an extracted or analyzed case. */
  available: boolean;
  disabled: boolean;
  onRun: (workflowId: string, workflowName: string) => void;
  onPickMode: (mode: ChatMode) => void;
}

/** Multi-agent workflows, recommended one first, plus the chat modes suggested for this case. */
export default function WorkflowPicker({ recommendations, available, disabled, onRun, onPickMode }: WorkflowPickerProps) {
  const t = useTranslations('chat');
  if (!available) {
    return (
      <div className="mb-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-center text-xs text-slate-500">
        {t('workflowsRequireData')}
      </div>
    );
  }

  const scores = new Map<string, number>();
  for (const recommendation of recommendations) {
    if (!scores.has(recommendation.id)) scores.set(recommendation.id, recommendation.score);
  }
  const top = topWorkflow(recommendations);
  const ordered = [...WORKFLOWS].sort((a, b) => (scores.get(b.id) ?? 0) - (scores.get(a.id) ?? 0));
  const suggestedModes = recommendations.filter(
    (item, index, all) => item.id.startsWith('agent:') && all.findIndex((other) => other.id === item.id) === index,
  );

  return (
    <div className="mb-2">
      <p className="mb-1.5 px-0.5 text-[11px] font-medium text-slate-500">{t('workflowsTitle')}</p>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
        {ordered.map((workflow) => {
          const Icon = workflow.icon;
          const name = t(workflow.nameKey);
          const isTop = top?.workflow.id === workflow.id;
          return (
            <button
              key={workflow.id}
              type="button"
              onClick={() => onRun(workflow.id, name)}
              disabled={disabled}
              className={clsx(
                'flex flex-col gap-1 rounded-lg border px-2.5 py-2 text-left transition hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-50',
                isTop ? workflow.highlightClass : 'border-slate-200 bg-white hover:border-slate-300',
              )}
            >
              <span className="flex items-center gap-1.5">
                <span className={clsx('flex h-6 w-6 flex-none items-center justify-center rounded-md', workflow.iconClass)}>
                  <Icon className="h-3.5 w-3.5" aria-hidden />
                </span>
                <span className="min-w-0 flex-1 truncate text-xs font-semibold text-slate-800">{name}</span>
                <span className="flex-none text-[10px] text-slate-400">{t(workflow.durationKey)}</span>
              </span>
              <span className="text-[10px] leading-snug text-slate-500">{t(workflow.patternKey)}</span>
              {isTop && top && (
                <span className="flex items-start gap-1 text-[10px] font-medium leading-snug text-fuchsia-700">
                  <Sparkles className="mt-px h-3 w-3 flex-none" aria-hidden />
                  <span className="sr-only">{t('recommended')}:</span>
                  {top.reason}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {suggestedModes.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1 px-0.5 text-[11px] text-slate-500">
          <span>{t('suggestedAgents')}</span>
          {suggestedModes.map((item) => {
            const mode = item.id.slice('agent:'.length) as ChatMode;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onPickMode(mode)}
                title={item.reason}
                className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600 transition-colors hover:bg-slate-200"
              >
                {MODE_LABEL_KEYS[mode] ? t(MODE_LABEL_KEYS[mode]) : mode}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface RecommendedWorkflowProps {
  recommendations: ChatRecommendation[];
  disabled: boolean;
  onRun: (workflowId: string, workflowName: string) => void;
}

/** One-click access to the workflow recommended for this case, shown in an empty conversation. */
export function RecommendedWorkflow({ recommendations, disabled, onRun }: RecommendedWorkflowProps) {
  const t = useTranslations('chat');
  const top = topWorkflow(recommendations);
  if (!top) return null;
  const Icon = top.workflow.icon;
  const name = t(top.workflow.nameKey);
  return (
    <button
      type="button"
      onClick={() => onRun(top.workflow.id, name)}
      disabled={disabled}
      className={clsx(
        'mx-auto mt-6 flex w-full max-w-md items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-50',
        top.workflow.highlightClass,
      )}
    >
      <span className={clsx('flex h-8 w-8 flex-none items-center justify-center rounded-lg', top.workflow.iconClass)}>
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500">{t('recommendedWorkflow')}</span>
        <span className="block text-sm font-semibold text-slate-900">
          {name} <span className="font-normal text-slate-400">· {t(top.workflow.durationKey)}</span>
        </span>
        <span className="block truncate text-xs text-slate-600" title={top.reason}>{top.reason}</span>
      </span>
      <span className="flex-none rounded-lg bg-slate-900 px-2.5 py-1 text-xs font-medium text-white">{t('runWorkflow')}</span>
    </button>
  );
}
