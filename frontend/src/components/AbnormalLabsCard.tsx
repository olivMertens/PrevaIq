'use client';

import React from 'react';
import { FlaskConical } from 'lucide-react';
import { PageRefBadges } from './PageRefBadge';
import type { AbnormalLabEntry } from '@/lib/types';
import { useTranslations } from 'next-intl';

interface AbnormalLabsCardProps {
  labs: AbnormalLabEntry[];
  onPageClick?: (page: number) => void;
  onPageHover?: (page: number, rect: DOMRect) => void;
  onPageLeave?: () => void;
}

function interpretationColor(interpretation: string | undefined) {
  if (!interpretation) return 'text-slate-600';
  const lower = interpretation.toLowerCase();
  if (lower.includes('critical') || lower.includes('very high') || lower.includes('very low')) return 'text-red-700 font-semibold';
  if (lower.includes('elevated') || lower.includes('high') || lower.includes('low')) return 'text-amber-700';
  return 'text-slate-600';
}

export default function AbnormalLabsCard({ labs, onPageClick, onPageHover, onPageLeave }: AbnormalLabsCardProps) {
  const t = useTranslations('labs');
  if (!labs || labs.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2 mb-2">
          <FlaskConical className="w-4 h-4 text-violet-500" /> {t('abnormalLabResults')}
        </h3>
        <p className="text-sm text-slate-500 italic">{t('noAbnormalResults')}</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2 mb-3">
          <FlaskConical className="w-4 h-4 text-violet-500" /> {t('abnormalLabResults')}
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium">{t('date')}</th>
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium">{t('test')}</th>
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium">{t('value')}</th>
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium">{t('refRange')}</th>
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium">{t('interpretation')}</th>
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium">{t('source')}</th>
            </tr>
          </thead>
          <tbody>
            {labs.map((lab, i) => (
              <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                <td className="py-1.5 px-2 text-slate-500">{lab.date}</td>
                <td className="py-1.5 px-2 font-medium text-slate-700">{lab.test_name}</td>
                <td className="py-1.5 px-2 text-slate-700">
                  {lab.value} {lab.unit}
                </td>
                <td className="py-1.5 px-2 text-slate-500">{lab.reference_range}</td>
                <td className={`py-1.5 px-2 ${interpretationColor(lab.interpretation)}`}>
                  {lab.interpretation}
                </td>
                <td className="py-1.5 px-2">
                  <PageRefBadges pages={lab.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
