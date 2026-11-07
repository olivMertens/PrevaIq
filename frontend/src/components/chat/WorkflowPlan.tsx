'use client';

import clsx from 'clsx';
import { AlertTriangle, Bot, CheckCircle2, ClipboardCheck, FileSearch, Globe, Loader2, Scale, ShieldAlert } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { WorkflowExecution, WorkflowStepStatus } from './types';

const AGENT_ROLES: Record<string, { key: string; icon: typeof Bot }> = {
  ExtractAgent: { key: 'extraction', icon: FileSearch },
  PolicyAgent: { key: 'policy', icon: FileSearch },
  AnalysisAgent: { key: 'analysis', icon: Scale },
  FraudAgent: { key: 'fraud', icon: ShieldAlert },
  FraudDetector: { key: 'fraud', icon: ShieldAlert },
  WebIntelligence: { key: 'web', icon: Globe },
  DecisionAgent: { key: 'decision', icon: ClipboardCheck },
  RiskAgent: { key: 'risk', icon: Scale },
  CrossChecker: { key: 'crossCheck', icon: ClipboardCheck },
};

export function WorkflowAgentLabel({ agent }: { agent: string }) {
  const t = useTranslations('chat');
  const role = AGENT_ROLES[agent];
  const Icon = role?.icon ?? Bot;
  return <span className="inline-flex min-w-0 items-center gap-1.5" title={agent}>
    <Icon className="h-4 w-4 flex-none" aria-hidden />
    <span>{role ? t(`workflowRoles.${role.key}`) : agent}</span>
  </span>;
}

function StepStatus({ status }: { status: WorkflowStepStatus }) {
  const t = useTranslations('chat');
  const Icon = status === 'running' ? Loader2 : status === 'completed' ? CheckCircle2
    : status === 'failed' || status === 'needs_review' ? AlertTriangle : null;
  return <span className={clsx('inline-flex items-center gap-1 text-xs', {
    'text-violet-700': status === 'running',
    'text-emerald-700': status === 'completed',
    'text-amber-800': status === 'needs_review' || status === 'failed',
    'text-slate-500': status === 'waiting',
  })}>
    {Icon && <Icon className={clsx('h-3.5 w-3.5 flex-none', status === 'running' && 'animate-spin')} aria-hidden />}
    {t(`workflowStepStatus.${status}`)}
  </span>;
}

export default function WorkflowPlan({ execution }: { execution: WorkflowExecution }) {
  const t = useTranslations('chat');
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3" aria-label={t('workflowPlanTitle')}>
      <h4 className="text-sm font-semibold text-slate-800">{t('workflowPlanTitle')}</h4>
      <p className="mt-1 text-xs leading-relaxed text-slate-500">{t('workflowPlanHelp')}</p>
      <ol className="mt-3 space-y-3">
        {execution.plan.map((stage, index) => (
          <li key={stage.id}>
            <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-700">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-100">{index + 1}</span>
              {t(`workflowStages.${stage.id}`)}
              {stage.id === 'context' && <StepStatus status={execution.context} />}
            </div>
            {stage.agents.length > 0 && <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {stage.agents.map(agent => {
                const step = execution.agents[agent];
                return <li key={agent} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-2.5 py-2 text-xs text-slate-700">
                  <WorkflowAgentLabel agent={agent} />
                  <StepStatus status={step?.status ?? 'waiting'} />
                </li>;
              })}
            </ul>}
          </li>
        ))}
      </ol>
    </section>
  );
}
