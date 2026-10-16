'use client';

import React from 'react';
import { AlertTriangle, Clock, Search, Stethoscope, ImageIcon, AlertCircle } from 'lucide-react';
import { PageRefBadges } from './PageRefBadge';
import type { PendingInvestigation, Urgency } from '@/lib/types';
import { useTranslations } from 'next-intl';

interface PendingInvestigationsCardProps {
  investigations: PendingInvestigation[];
  summary?: string;
  onPageClick?: (page: number) => void;
  onPageHover?: (page: number, rect: DOMRect) => void;
  onPageLeave?: () => void;
}

const urgencyConfig: Record<Urgency, { className: string; icon: React.ReactNode; label: string }> = {
  high: {
    className: 'bg-red-50 text-red-700 border-red-200',
    icon: <AlertTriangle className="w-3 h-3" />,
    label: 'HIGH',
  },
  medium: {
    className: 'bg-amber-50 text-amber-700 border-amber-200',
    icon: <Clock className="w-3 h-3" />,
    label: 'MEDIUM',
  },
  low: {
    className: 'bg-slate-50 text-slate-600 border-slate-200',
    icon: <Search className="w-3 h-3" />,
    label: 'LOW',
  },
};

const typeIcons: Record<string, React.ReactNode> = {
  test: <Search className="w-4 h-4" />,
  referral: <Stethoscope className="w-4 h-4" />,
  consult: <Stethoscope className="w-4 h-4" />,
  imaging: <ImageIcon className="w-4 h-4" />,
  procedure: <Clock className="w-4 h-4" />,
};

export default function PendingInvestigationsCard({
  investigations,
  summary,
  onPageClick,
  onPageHover,
  onPageLeave,
}: PendingInvestigationsCardProps) {
  const t = useTranslations('common');
  if (!investigations || investigations.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2 mb-2">
          <AlertCircle className="w-4 h-4 text-red-500" /> Pending Investigations
        </h3>
        <p className="text-sm text-slate-500 italic">{t('noPendingInvestigations')}</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border-l-4 border-l-red-400 border border-slate-200 p-4">
      <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2 mb-1">
        <AlertCircle className="w-4 h-4 text-red-500" /> Pending Investigations
      </h3>
      {summary && <p className="text-xs text-slate-500 mb-3">{summary}</p>}
      <div className="space-y-2">
        {investigations.map((inv, i) => {
          const urg = urgencyConfig[inv.urgency] || urgencyConfig.low;
          return (
            <div
              key={i}
              className="flex items-start gap-3 p-2.5 rounded-lg bg-slate-50 border border-slate-100"
            >
              <div className="flex-shrink-0 mt-0.5 text-slate-400">
                {typeIcons[inv.type] || <Search className="w-4 h-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  {inv.date && (
                    <span className="text-xs font-medium text-slate-500">{inv.date}</span>
                  )}
                  <span
                    className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border ${urg.className}`}
                  >
                    {urg.icon}
                    {urg.label}
                  </span>
                  <span className="text-[10px] text-slate-400 capitalize">{inv.type}</span>
                </div>
                <p className="text-sm text-slate-700 leading-snug">
                  {inv.description}
                  <PageRefBadges pages={inv.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
