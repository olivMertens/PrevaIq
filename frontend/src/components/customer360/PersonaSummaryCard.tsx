'use client';

import { useState } from 'react';
import {
  ClipboardList,
  Stethoscope,
  Car,
  Home,
  CloudRain,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Clock,
  AlertTriangle,
  XCircle,
  Activity,
} from 'lucide-react';
import type { PersonaSummary } from '@/lib/customer360-types';
import { useTranslations } from 'next-intl';
import clsx from 'clsx';
import Link from 'next/link';

interface PersonaSummaryCardProps {
  summary: PersonaSummary;
}

const PERSONA_THEME: Record<string, { icon: typeof ClipboardList; color: string; gradient: string; bg: string; border: string }> = {
  underwriting: { icon: ClipboardList, color: 'text-indigo-700', gradient: 'from-indigo-500 to-indigo-600', bg: 'bg-indigo-50', border: 'border-indigo-200' },
  life_health_claims: { icon: Stethoscope, color: 'text-cyan-700', gradient: 'from-cyan-500 to-cyan-600', bg: 'bg-cyan-50', border: 'border-cyan-200' },
  automotive_claims: { icon: Car, color: 'text-red-700', gradient: 'from-red-500 to-red-600', bg: 'bg-red-50', border: 'border-red-200' },
  habitation_claims: { icon: CloudRain, color: 'text-blue-700', gradient: 'from-blue-500 to-blue-600', bg: 'bg-blue-50', border: 'border-blue-200' },
  property_casualty_claims: { icon: CloudRain, color: 'text-blue-700', gradient: 'from-blue-500 to-blue-600', bg: 'bg-blue-50', border: 'border-blue-200' },
  mortgage_underwriting: { icon: Home, color: 'text-emerald-700', gradient: 'from-emerald-500 to-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-200' },
};

const STATUS_DISPLAY: Record<string, { icon: typeof CheckCircle2; color: string; labelKey: string }> = {
  approved: { icon: CheckCircle2, color: 'text-emerald-600', labelKey: 'statusApproved' },
  approuve: { icon: CheckCircle2, color: 'text-emerald-600', labelKey: 'statusApproved' },
  completed: { icon: CheckCircle2, color: 'text-emerald-600', labelKey: 'statusCompleted' },
  closed: { icon: CheckCircle2, color: 'text-slate-500', labelKey: 'statusClosed' },
  clos: { icon: CheckCircle2, color: 'text-slate-500', labelKey: 'statusClosed' },
  actif: { icon: CheckCircle2, color: 'text-emerald-600', labelKey: 'statusActive' },
  conditional: { icon: AlertTriangle, color: 'text-amber-600', labelKey: 'statusConditional' },
  referred: { icon: Clock, color: 'text-amber-600', labelKey: 'statusReferred' },
  pending: { icon: Clock, color: 'text-blue-600', labelKey: 'statusPending' },
  en_attente: { icon: Clock, color: 'text-blue-600', labelKey: 'statusPending' },
  in_progress: { icon: Clock, color: 'text-blue-600', labelKey: 'statusInProgress' },
  en_cours: { icon: Clock, color: 'text-blue-600', labelKey: 'statusInProgress' },
  investigating: { icon: Activity, color: 'text-orange-600', labelKey: 'statusInvestigating' },
  investigation: { icon: Activity, color: 'text-orange-600', labelKey: 'statusInvestigating' },
  declined: { icon: XCircle, color: 'text-rose-600', labelKey: 'statusDeclined' },
};

const RISK_COLORS: Record<string, string> = {
  low: 'text-emerald-600',
  medium: 'text-amber-600',
  high: 'text-rose-600',
};

export default function PersonaSummaryCard({ summary }: PersonaSummaryCardProps) {
  const t = useTranslations('customer360');
  const [expanded, setExpanded] = useState(false);
  const theme = PERSONA_THEME[summary.persona] || PERSONA_THEME.underwriting;
  const PersonaIcon = theme.icon;
  const statusInfo = STATUS_DISPLAY[summary.latest_status] || STATUS_DISPLAY.pending;
  const StatusIcon = statusInfo.icon;

  // Highlight metrics to show in the card header
  const highlightMetrics = getHighlightMetrics(summary, t);

  return (
    <div className={clsx('rounded-xl border overflow-hidden transition-shadow hover:shadow-md', theme.border, 'bg-white')}>
      {/* Gradient top bar */}
      <div className={clsx('h-1 bg-gradient-to-r', theme.gradient)} />

      <div className="p-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={clsx('w-10 h-10 rounded-lg flex items-center justify-center', theme.bg)}>
              <PersonaIcon className={clsx('w-5 h-5', theme.color)} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">{summary.persona_label}</h3>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span>{t('dossierCount', { count: summary.application_count })}</span>
                {summary.risk_level && (
                  <>
                    <span>•</span>
                    <span className={clsx('font-medium', RISK_COLORS[summary.risk_level] || 'text-slate-600')}>
                      {t(summary.risk_level === 'low' ? 'riskLabelLow' : summary.risk_level === 'medium' ? 'riskLabelMedium' : 'riskLabelHigh')}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <StatusIcon className={clsx('w-4 h-4', statusInfo.color)} />
            <span className={clsx('text-xs font-medium', statusInfo.color)}>{t(statusInfo.labelKey)}</span>
          </div>
        </div>

        {/* Highlight metrics */}
        {highlightMetrics.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-3">
            {highlightMetrics.map(metric => (
              <div key={metric.label} className="bg-slate-50 rounded-lg px-3 py-2">
                <div className="text-xs text-slate-500">{metric.label}</div>
                <div className={clsx('text-sm font-semibold', metric.color || 'text-slate-900')}>{metric.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        {summary.applications.length > 0 && (
          <div className="flex items-center gap-4 mt-4">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 transition-colors"
            >
              {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              {expanded ? t('hideDetails') : t('showDetails')}
            </button>
            <Link
              href={`/?app=${summary.applications[0].application_id}&persona=${mapPersonaToFrontendId(summary.persona)}`}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-600 transition-colors"
            >
              {t('openWorkbench')}
            </Link>
          </div>
        )}

        {expanded && (
          <div className="mt-3 space-y-2">
            {summary.applications.map((app, idx) => {
              const appStatus = STATUS_DISPLAY[app.status] || STATUS_DISPLAY.pending;
              const AppStatusIcon = appStatus.icon;
              return (
                <div key={`${app.application_id}-${idx}`} className="flex items-start gap-2 p-3 bg-slate-50 rounded-lg">
                  <AppStatusIcon className={clsx('w-4 h-4 mt-0.5 shrink-0', appStatus.color)} />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-slate-900">{app.title}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{formatDate(app.date)}</div>
                    <div className="text-xs text-slate-600 mt-1 leading-relaxed">{app.summary}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

interface MetricHighlight {
  label: string;
  value: string;
  color?: string;
}

function getHighlightMetrics(summary: PersonaSummary, t: (key: string) => string): MetricHighlight[] {
  const metrics: MetricHighlight[] = [];
  const km = summary.key_metrics;

  if (summary.persona === 'underwriting') {
    if (km.decision) metrics.push({ label: t('decision'), value: km.decision, color: getDecisionColor(km.decision) });
    if (km.risk_class) metrics.push({ label: t('riskClass'), value: km.risk_class });
    if (km.coverage_amount) metrics.push({ label: t('coverage'), value: km.coverage_amount });
    if (km.monthly_premium) metrics.push({ label: t('premium'), value: km.monthly_premium });
  } else if (summary.persona === 'mortgage_underwriting') {
    if (km.decision) metrics.push({ label: t('decision'), value: km.decision, color: getDecisionColor(km.decision) });
    if (km.gds_ratio) metrics.push({ label: t('debtRatio'), value: km.gds_ratio, color: parseFloat(km.gds_ratio) > 35 ? 'text-rose-600' : undefined });
    if (km.tds_ratio) metrics.push({ label: t('totalDebtRatio'), value: km.tds_ratio, color: parseFloat(km.tds_ratio) > 35 ? 'text-rose-600' : undefined });
    if (km.ltv) metrics.push({ label: t('ltv'), value: km.ltv });
  } else if (summary.persona === 'automotive_claims' || summary.persona === 'life_health_claims') {
    if (km.decision) metrics.push({ label: t('decision'), value: km.decision, color: getDecisionColor(km.decision) });
    if (km.payout) metrics.push({ label: t('payout'), value: km.payout });
    if (km.fraud_risk) metrics.push({ label: t('fraudRisk'), value: km.fraud_risk, color: km.fraud_risk === 'High' ? 'text-rose-600' : undefined });
    if (km.repair_estimate) metrics.push({ label: t('repairEstimate'), value: km.repair_estimate });
  }

  return metrics.slice(0, 4);
}

function mapPersonaToFrontendId(persona: string): string {
  if (persona === 'mortgage_underwriting') return 'mortgage';
  return persona;
}

function getDecisionColor(decision: string): string {
  const d = decision.toLowerCase();
  if (d.includes('approved') || d === 'approved') return 'text-emerald-600';
  if (d.includes('conditional')) return 'text-amber-600';
  if (d.includes('declined') || d.includes('denied')) return 'text-rose-600';
  if (d.includes('referred') || d.includes('pending') || d.includes('investigation')) return 'text-amber-600';
  return 'text-slate-900';
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('fr-FR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}
