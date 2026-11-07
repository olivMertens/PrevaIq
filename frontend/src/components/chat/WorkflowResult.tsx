'use client';

import clsx from 'clsx';
import { AlertTriangle, CheckCircle2, ChevronRight } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { StructuredContentRenderer } from './ChatCards';
import { agentDisplayText } from './agentText';
import type { WorkflowRunResult } from './types';
import WorkflowPlan, { WorkflowAgentLabel } from './WorkflowPlan';

interface WorkflowResultProps {
  result: WorkflowRunResult;
  onPolicyClick?: (policyId: string) => void;
}

/** Workflow outcome: the synthesis first, each contributing agent's output on demand. */
export default function WorkflowResult({ result, onPolicyClick }: WorkflowResultProps) {
  const t = useTranslations('chat');
  const needsReview = result.status === 'needs_review';
  const synthesizer = result.steps[result.steps.length - 1]?.agent;
  // The last step is the synthesis, already shown as the summary.
  const contributors = result.steps.slice(0, -1);

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-900">{result.name}</span>
        <span
          className={clsx(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1',
            needsReview
              ? 'bg-amber-50 text-amber-800 ring-amber-200'
              : 'bg-emerald-50 text-emerald-700 ring-emerald-200',
          )}
        >
          {needsReview ? <AlertTriangle className="h-3 w-3" aria-hidden /> : <CheckCircle2 className="h-3 w-3" aria-hidden />}
          {needsReview ? t('workflowNeedsReviewStatus') : t('workflowCompletedStatus')}
        </span>
        <span className="ml-auto text-[11px] text-slate-400">
          {t('workflowMeta', { agents: result.steps.length, seconds: Math.max(1, Math.round(result.durationMs / 1000)) })}
        </span>
      </div>

      <div>
        {synthesizer && (
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs font-medium text-slate-600">
            <span className="font-semibold text-slate-800">{t('workflowSummary')}</span>
            <WorkflowAgentLabel agent={synthesizer} />
          </div>
        )}
        <StructuredContentRenderer content={agentDisplayText(result.summary, t)} onPolicyClick={onPolicyClick} />
      </div>

      {result.execution && <WorkflowPlan execution={result.execution} />}
      {contributors.length > 0 && (
        <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          <p className="px-3 py-2 text-xs font-semibold text-slate-700">{t('workflowContributions')}</p>
          {contributors.map((step, index) => (
            <details key={`${step.agent}-${index}`} className="group">
              <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
                <ChevronRight className="h-3.5 w-3.5 text-slate-400 transition-transform group-open:rotate-90" aria-hidden />
                <WorkflowAgentLabel agent={step.agent} />
              </summary>
              <div className="px-3 pb-2 pt-1">
                <StructuredContentRenderer content={agentDisplayText(step.text, t)} onPolicyClick={onPolicyClick} />
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
