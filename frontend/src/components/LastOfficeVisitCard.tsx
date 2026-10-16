'use client';

import React from 'react';
import { Calendar, ClipboardList, FlaskConical, FileText } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { PageRefBadges } from './PageRefBadge';
import type { LastOfficeVisitData, LastLabsData } from '@/lib/types';

interface LastOfficeVisitCardProps {
  lov: LastOfficeVisitData | null;
  lastLabs: LastLabsData | null;
  onPageClick?: (page: number) => void;
  onPageHover?: (page: number, rect: DOMRect) => void;
  onPageLeave?: () => void;
}

export default function LastOfficeVisitCard({ lov, lastLabs, onPageClick, onPageHover, onPageLeave }: LastOfficeVisitCardProps) {
  const t = useTranslations('body');
  if (!lov && !lastLabs) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2 mb-2">
          <FileText className="w-4 h-4 text-blue-500" /> {t('lovTitle')}
        </h3>
        <p className="text-sm text-slate-500 italic">{t('noLovData')}</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2 mb-3">
        <FileText className="w-4 h-4 text-blue-500" /> {t('lovTitle')}
      </h3>

      {/* LOV Section */}
      {lov && (
        <div className="mb-3">
          <div className="flex items-center gap-2 mb-1">
            <Calendar className="w-3.5 h-3.5 text-indigo-500" />
            <span className="text-xs font-semibold text-indigo-600 uppercase">{t('lastOfficeVisit')}</span>
            {lov.date && <span className="text-xs font-medium text-slate-600">{lov.date}</span>}
            <PageRefBadges pages={lov.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
          </div>
          <p className="text-sm text-slate-700 leading-snug ml-5">{lov.summary}</p>
          {lov.follow_up_plans && lov.follow_up_plans.length > 0 && (
            <div className="mt-2 ml-5">
              <div className="flex items-center gap-1.5 mb-1">
                <ClipboardList className="w-3 h-3 text-slate-400" />
                <span className="text-[10px] font-semibold text-slate-500 uppercase">{t('followUpPlans')}</span>
              </div>
              <ul className="list-disc list-inside text-xs text-slate-600 space-y-0.5">
                {lov.follow_up_plans.map((plan, i) => (
                  <li key={i}>{plan}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Last Labs Section */}
      {lastLabs && (
        <div className={lov ? 'border-t border-slate-100 pt-3' : ''}>
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="w-3.5 h-3.5 text-emerald-500" />
            <span className="text-xs font-semibold text-emerald-600 uppercase">{t('lastLabs')}</span>
            {lastLabs.date && <span className="text-xs font-medium text-slate-600">{lastLabs.date}</span>}
            <PageRefBadges pages={lastLabs.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
          </div>
          <p className="text-sm text-slate-700 leading-snug ml-5">{lastLabs.summary}</p>
        </div>
      )}
    </div>
  );
}
