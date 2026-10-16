'use client';

import {
  Loader2,
  Activity,
  Clock,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';

export function getStatusConfig(status: string, processingStatus?: string | null, t?: (key: string) => string) {
  const label = t || ((k: string) => k);
  
  if (processingStatus === 'extracting') {
    return { label: label('dataAgentRunning'), bg: 'bg-sky-50', text: 'text-sky-700', border: 'border-sky-200', icon: Loader2, animate: true };
  }
  if (processingStatus === 'analyzing') {
    return { label: label('riskAgentWorking'), bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200', icon: Activity, animate: true };
  }

  const configs: Record<string, { label: string; bg: string; text: string; border: string; icon: typeof Clock; animate?: boolean }> = {
    pending: { label: label('pending'), bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', icon: Clock },
    uploaded: { label: label('pending'), bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', icon: Clock },
    extracted: { label: label('extractionDone'), bg: 'bg-teal-50', text: 'text-teal-700', border: 'border-teal-200', icon: CheckCircle2 },
    extracting: { label: label('dataAgentRunning'), bg: 'bg-sky-50', text: 'text-sky-700', border: 'border-sky-200', icon: Loader2, animate: true },
    analyzing: { label: label('riskAgentWorking'), bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200', icon: Activity, animate: true },
    completed: { label: label('readyForReview'), bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', icon: CheckCircle2 },
    error: { label: label('errorLabel'), bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200', icon: AlertTriangle },
  };
  return configs[status] || configs.pending;
}

export default function StatusBadge({ status, processingStatus }: { status: string; processingStatus?: string | null }) {
  const t = useTranslations('dashboard');
  const config = getStatusConfig(status, processingStatus, t);
  const Icon = config.icon;
  return (
    <span className={clsx(
      'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border',
      config.bg, config.text, config.border
    )}>
      <Icon className={clsx('w-3 h-3', config.animate && 'animate-spin')} />
      {config.label}
    </span>
  );
}
