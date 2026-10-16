'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Pill, Stethoscope, ImageIcon, Brain, Ear, Eye, Smile, Heart, Wind, Activity, Baby, Scale, Bone, Droplet, Zap, Shield, Sparkles, Search } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { PageRefBadges } from './PageRefBadge';
import type { BodySystemEntry, DiagnosisEntry, Severity } from '@/lib/types';

interface BodySystemCardProps {
  system: BodySystemEntry;
  onPageClick?: (page: number) => void;
  onPageHover?: (page: number, rect: DOMRect) => void;
  onPageLeave?: () => void;
  isHighlighted?: boolean;
}

const severityBadgeStyle: Record<Severity, string> = {
  high: 'bg-red-100 text-red-700 border-red-200',
  moderate: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  normal: 'bg-slate-100 text-slate-600 border-slate-200',
};

const systemIcons: Record<string, React.ReactNode> = {
  NEURO: <Brain className="w-4 h-4 text-purple-500" />,
  ENT: <Ear className="w-4 h-4 text-orange-500" />,
  EYES: <Eye className="w-4 h-4 text-blue-500" />,
  DENTAL: <Smile className="w-4 h-4 text-slate-500" />,
  CV: <Heart className="w-4 h-4 text-red-500" />,
  RESP: <Wind className="w-4 h-4 text-cyan-500" />,
  BREAST: <Activity className="w-4 h-4 text-pink-500" />,
  GI: <Activity className="w-4 h-4 text-amber-500" />,
  HEPATIC: <Activity className="w-4 h-4 text-orange-500" />,
  RENAL: <Droplet className="w-4 h-4 text-blue-500" />,
  GU: <Droplet className="w-4 h-4 text-teal-500" />,
  REPRO: <Baby className="w-4 h-4 text-pink-500" />,
  MSK: <Bone className="w-4 h-4 text-slate-500" />,
  VASC: <Activity className="w-4 h-4 text-red-500" />,
  ENDO: <Zap className="w-4 h-4 text-yellow-500" />,
  HEME: <Droplet className="w-4 h-4 text-red-500" />,
  DERM: <Sparkles className="w-4 h-4 text-violet-500" />,
  PSYCH: <Brain className="w-4 h-4 text-indigo-500" />,
  IMMUNE: <Shield className="w-4 h-4 text-emerald-500" />,
  BUILD: <Scale className="w-4 h-4 text-slate-500" />,
};

function DiagnosisDetail({
  dx,
  isExpanded,
  onToggle,
  onPageClick,
  onPageHover,
  onPageLeave,
}: {
  dx: DiagnosisEntry;
  isExpanded: boolean;
  onToggle: () => void;
  onPageClick?: (page: number) => void;
  onPageHover?: (page: number, rect: DOMRect) => void;
  onPageLeave?: () => void;
}) {
  const t = useTranslations('body');
  const statusColors: Record<string, string> = {
    active: 'text-red-600',
    resolved: 'text-emerald-600',
    monitoring: 'text-amber-600',
    unknown: 'text-slate-500',
  };

  return (
    <div className="border border-slate-100 rounded-lg overflow-hidden">
      {/* Diagnosis header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 p-2.5 hover:bg-slate-50 transition-colors text-left"
      >
        {isExpanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
        )}
        <span className="text-sm font-medium text-slate-800 flex-1">{dx.name}</span>
        <span className={`text-[10px] font-medium ${statusColors[dx.status] || 'text-slate-500'}`}>
          {dx.status}
        </span>
        {dx.date_diagnosed && (
          <span className="text-[10px] text-slate-400">dx {dx.date_diagnosed}</span>
        )}
        <PageRefBadges pages={dx.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
      </button>

      {/* Expanded details */}
      {isExpanded && (
        <div className="px-3 pb-3 pt-1 space-y-2 bg-slate-50/50">
          {/* Treatments */}
          {dx.treatments && dx.treatments.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <Pill className="w-3 h-3 text-blue-500" />
                <span className="text-[10px] font-semibold text-slate-500 uppercase">{t('treatments')}</span>
              </div>
              <div className="space-y-1 ml-4">
                {dx.treatments.map((tx, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-slate-600">
                    <span className="text-slate-400 flex-shrink-0">{tx.date}</span>
                    <span className="flex-1">{tx.description}</span>
                    <PageRefBadges pages={tx.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Consults */}
          {dx.consults && dx.consults.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <Stethoscope className="w-3 h-3 text-violet-500" />
                <span className="text-[10px] font-semibold text-slate-500 uppercase">{t('consults')}</span>
              </div>
              <div className="space-y-1 ml-4">
                {dx.consults.map((c, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-slate-600">
                    <span className="text-slate-400 flex-shrink-0">{c.date}</span>
                    <span className="font-medium text-slate-700">{c.specialist}</span>
                    <span className="flex-1">— {c.summary}</span>
                    <PageRefBadges pages={c.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Imaging */}
          {dx.imaging && dx.imaging.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <ImageIcon className="w-3 h-3 text-teal-500" />
                <span className="text-[10px] font-semibold text-slate-500 uppercase">{t('imaging')}</span>
              </div>
              <div className="space-y-1 ml-4">
                {dx.imaging.map((img, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-slate-600">
                    <span className="text-slate-400 flex-shrink-0">{img.date}</span>
                    <span className="font-medium text-slate-700">{img.type}</span>
                    <span className="flex-1">— {img.result}</span>
                    <PageRefBadges pages={img.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BodySystemCard({ system, onPageClick, onPageHover, onPageLeave, isHighlighted }: BodySystemCardProps) {
  const t = useTranslations('body');
  const [expandedDx, setExpandedDx] = useState<Set<number>>(new Set([0]));

  const toggleDx = (index: number) => {
    setExpandedDx((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const badgeClass = severityBadgeStyle[system.severity] || severityBadgeStyle.normal;
  const badgeLabel = t(system.severity);
  const icon = systemIcons[system.system_code] || <Search className="w-4 h-4 text-slate-400" />;

  return (
    <div
      className={`bg-white rounded-lg border p-4 transition-all duration-300 ${
        isHighlighted
          ? 'border-indigo-300 ring-2 ring-indigo-100'
          : 'border-slate-200'
      }`}
    >
      {/* System header */}
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h4 className="text-sm font-semibold text-slate-800 flex-1">
          {system.system_name} ({system.system_code})
        </h4>
        <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-semibold rounded-full border ${badgeClass}`}>
          {badgeLabel}
        </span>
      </div>

      {/* Diagnoses */}
      <div className="space-y-2">
        {system.diagnoses.map((dx, i) => (
          <DiagnosisDetail
            key={i}
            dx={dx}
            isExpanded={expandedDx.has(i)}
            onToggle={() => toggleDx(i)}
            onPageClick={onPageClick}
            onPageHover={onPageHover}
            onPageLeave={onPageLeave}
          />
        ))}
      </div>
    </div>
  );
}
