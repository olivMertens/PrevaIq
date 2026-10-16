'use client';

import { useState } from 'react';
import { ShieldAlert, RefreshCw, AlertTriangle, Info, ShieldCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';
import clsx from 'clsx';
import type { ApplicationMetadata, SouscriaRiskContext } from '@/lib/types';
import { getSouscriaContext } from '@/lib/api';

interface SouscriaContextPanelProps {
  application: ApplicationMetadata;
}

const SEVERITY_STYLE: Record<string, { badge: string; labelKey: string; icon: typeof AlertTriangle }> = {
  critical: { badge: 'bg-rose-100 text-rose-700 border-rose-200', labelKey: 'severityCritical', icon: ShieldAlert },
  high: { badge: 'bg-orange-100 text-orange-700 border-orange-200', labelKey: 'severityHigh', icon: AlertTriangle },
  warning: { badge: 'bg-amber-100 text-amber-700 border-amber-200', labelKey: 'severityWarning', icon: AlertTriangle },
  medium: { badge: 'bg-amber-100 text-amber-700 border-amber-200', labelKey: 'severityMedium', icon: AlertTriangle },
  info: { badge: 'bg-sky-100 text-sky-700 border-sky-200', labelKey: 'severityInfo', icon: Info },
};

export default function SouscriaContextPanel({ application }: SouscriaContextPanelProps) {
  const t = useTranslations('souscria');
  const [ctx, setCtx] = useState<SouscriaRiskContext | null | undefined>(
    application.souscria_context ?? undefined
  );
  const [refreshing, setRefreshing] = useState(false);

  // Self-hide unless this dossier carries a Souscr'IA thread context.
  if (!ctx) return null;

  async function refresh() {
    setRefreshing(true);
    try {
      const fresh = await getSouscriaContext(application.id);
      if (fresh) setCtx(fresh);
    } catch {
      // graceful: keep showing the last known context
    } finally {
      setRefreshing(false);
    }
  }

  const sev = (ctx.max_severity || 'info').toLowerCase();
  const sevStyle = SEVERITY_STYLE[sev] || SEVERITY_STYLE.info;
  const SevIcon = sevStyle.icon;
  const fraudScore = ctx.fraud_score ?? ctx.fraud?.score ?? 0;
  const fraudSignals = ctx.fraud?.signals ?? [];
  const disclaimer = ctx.fraud_disclaimer ?? ctx.fraud?.disclaimer;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-violet-50 flex items-center justify-center">
            <ShieldAlert className="w-5 h-5 text-violet-600" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
              {t('contextTitle')}
              {ctx.alerts.length > 0 && (
                <span className={clsx('text-xs font-medium px-2 py-0.5 rounded-full border', sevStyle.badge)}>
                  {t(sevStyle.labelKey)}
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-500">{t('contextSubtitle')}</p>
          </div>
        </div>
        <button
          onClick={refresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={clsx('w-3.5 h-3.5', refreshing && 'animate-spin')} />
          {refreshing ? t('refreshing') : t('refresh')}
        </button>
      </div>

      {/* Alerts */}
      <section className="mb-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          {t('alerts')} ({ctx.alert_count})
        </h4>
        {ctx.alerts.length === 0 ? (
          <p className="text-sm text-slate-400 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            {t('noAlerts')}
          </p>
        ) : (
          <ul className="space-y-2">
            {ctx.alerts.map((a, idx) => {
              const aStyle = SEVERITY_STYLE[(a.severity || 'info').toLowerCase()] || SEVERITY_STYLE.info;
              const AIcon = aStyle.icon;
              return (
                <li key={idx} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <AIcon className="w-4 h-4 text-slate-400 shrink-0" />
                    <span className={clsx('text-xs font-medium px-2 py-0.5 rounded-full border', aStyle.badge)}>
                      {t(aStyle.labelKey)}
                    </span>
                    {a.category && <span className="text-xs text-slate-500">{a.category}</span>}
                    {a.handoff_human && (
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-rose-50 text-rose-600">
                        {t('handoffHuman')}
                      </span>
                    )}
                  </div>
                  {a.reason && <p className="text-sm font-medium text-slate-800">{a.reason}</p>}
                  {a.excerpt && <p className="text-xs text-slate-500 mt-0.5 italic">“{a.excerpt}”</p>}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Fraud signals (suspicion only) */}
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          {t('fraudSignals')}
        </h4>
        <p className="text-sm text-slate-700 mb-1">{t('fraudScore', { score: fraudScore })}</p>
        {fraudSignals.length === 0 ? (
          <p className="text-sm text-slate-400">{t('noFraudSignals')}</p>
        ) : (
          <ul className="list-disc list-inside text-sm text-slate-600 space-y-0.5">
            {fraudSignals.map((s, idx) => (
              <li key={idx}>{String((s as { label?: string }).label ?? JSON.stringify(s))}</li>
            ))}
          </ul>
        )}
        {disclaimer && <p className="text-xs text-slate-400 mt-2 italic">{disclaimer}</p>}
      </section>

      {ctx.thread_id && (
        <p className="text-[11px] text-slate-400 mt-4 pt-3 border-t border-slate-100">
          {t('sourceThread', { thread: ctx.thread_id })}
        </p>
      )}
    </div>
  );
}
