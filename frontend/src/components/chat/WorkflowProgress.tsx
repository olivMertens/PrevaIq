'use client';

import { Bot, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import WorkflowPlan from './WorkflowPlan';
import type { WorkflowExecution } from './types';

export default function WorkflowProgress({ execution }: { execution: WorkflowExecution }) {
  const t = useTranslations('chat');

  return (
    <div className="flex justify-start gap-3" role="status" aria-live="polite">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-violet-100">
        <Bot className="h-5 w-5 text-violet-600" />
      </div>
      <div className="min-w-0 flex-1 rounded-lg border border-violet-200 bg-violet-50 px-4 py-3">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-violet-600" aria-hidden />
          <span className="text-sm font-medium text-violet-700">
            {execution.plan.length ? t('workflowRunning') : t('workflowConnecting')}
          </span>
        </div>
        {execution.plan.length > 0 && <div className="mt-3"><WorkflowPlan execution={execution} /></div>}
      </div>
    </div>
  );
}
