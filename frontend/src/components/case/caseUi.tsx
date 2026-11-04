'use client';

import { Brain, Calendar, Camera, FileText, Globe, Info, ListChecks, OctagonAlert, Scale, Sparkles, TriangleAlert } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import type { SignalSeverity, SignalSource } from './caseSignals';

// Severity is always conveyed by an icon shape and a word, never by color alone.
export const SEVERITY_STYLE: Record<SignalSeverity, { Icon: typeof OctagonAlert; icon: string; text: string; surface: string }> = {
  critical: { Icon: OctagonAlert, icon: 'text-rose-600', text: 'text-rose-700', surface: 'border-rose-200 bg-rose-50' },
  warning: { Icon: TriangleAlert, icon: 'text-amber-600', text: 'text-amber-800', surface: 'border-amber-200 bg-amber-50' },
  info: { Icon: Info, icon: 'text-sky-700', text: 'text-sky-800', surface: 'border-sky-200 bg-sky-50' },
};

export function SeverityIcon({ severity, className }: { severity: SignalSeverity; className?: string }) {
  const { Icon, icon } = SEVERITY_STYLE[severity];
  return <Icon className={clsx('h-5 w-5 flex-shrink-0', icon, className)} aria-hidden />;
}

const SOURCE_ICON: Record<SignalSource, typeof Camera> = {
  photoAnalysis: Camera,
  declarationCheck: FileText,
  fraudModel: Brain,
  webIq: Globe,
  policy: Scale,
  rule: ListChecks,
  fileDates: Calendar,
  aiAnalysis: Sparkles,
};

export function SourceChip({ source }: { source: SignalSource }) {
  const t = useTranslations('caseCockpit.sources');
  const Icon = SOURCE_ICON[source];
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs',
        source === 'webIq' ? 'bg-sky-50 text-sky-800' : 'bg-slate-100 text-slate-700',
      )}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {t(source)}
    </span>
  );
}

/** Section card with a real heading, used by every cockpit block. */
export function CockpitCard({
  title,
  headingId,
  aside,
  children,
  className,
}: {
  title: string;
  headingId: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section aria-labelledby={headingId} className={clsx('rounded-xl border border-slate-200 bg-white shadow-sm', className)}>
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <h2 id={headingId} className="text-base font-semibold text-slate-900">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
