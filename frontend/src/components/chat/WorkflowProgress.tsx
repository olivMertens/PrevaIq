'use client';

import { useEffect, useState } from 'react';
import { Bot, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

// Stages of each workflow and when they usually start (ms): the API answers only once,
// so the current stage is estimated.
const PHASES: Record<string, { key: string; at: number }[]> = {
  express: [
    { key: 'workflowPhaseExtract', at: 0 },
    { key: 'workflowPhaseDecision', at: 8000 },
  ],
  complet: [
    { key: 'workflowPhaseExtract', at: 0 },
    { key: 'workflowPhaseAnalysis', at: 10000 },
    { key: 'workflowPhaseRisk', at: 40000 },
  ],
  fraude: [
    { key: 'workflowPhaseFraud', at: 0 },
    { key: 'workflowPhaseWebIntel', at: 15000 },
    { key: 'workflowPhaseCrossCheck', at: 35000 },
  ],
};

/** Running workflow: estimated current stage and progress segments. */
export default function WorkflowProgress({ workflowId }: { workflowId: string }) {
  const t = useTranslations('chat');
  const [current, setCurrent] = useState(0);
  const phases = PHASES[workflowId] ?? [];

  useEffect(() => {
    const timers = (PHASES[workflowId] ?? [])
      .slice(1)
      .map((phase, index) => setTimeout(() => setCurrent(index + 1), phase.at));
    return () => timers.forEach(clearTimeout);
  }, [workflowId]);

  return (
    <div className="flex justify-start gap-3" role="status" aria-live="polite">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-violet-100">
        <Bot className="h-5 w-5 text-violet-600" />
      </div>
      <div className="min-w-[240px] rounded-lg border border-violet-200 bg-violet-50 px-4 py-3">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-violet-600" aria-hidden />
          <span className="text-sm font-medium text-violet-700">
            {phases[current] ? t(phases[current].key) : t('workflowRunning')}
          </span>
        </div>
        <div className="mt-2 flex gap-1">
          {phases.map((phase, index) => (
            <div
              key={phase.key}
              className={`h-1.5 flex-1 rounded-full transition-colors duration-700 ${
                index === current ? 'animate-pulse bg-violet-500' : index < current ? 'bg-violet-300' : 'bg-violet-100'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
