'use client';

import { Sparkles, FileText, UserCog, Target } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { SouscriaAcquisition } from '@/lib/customer360-types';

interface SouscriaAcquisitionCardProps {
  data: SouscriaAcquisition;
}

const SOURCE_BADGE =
  'text-xs font-medium px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200';

export default function SouscriaAcquisitionCard({ data }: SouscriaAcquisitionCardProps) {
  const t = useTranslations('souscria');
  const advisor = data.advisor;

  return (
    <div className="bg-white rounded-xl border border-violet-200 shadow-sm p-6">
      <div className="flex items-start justify-between mb-5">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-violet-50 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-violet-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{t('acquisitionTitle')}</h2>
            <p className="text-xs text-slate-500">{t('acquisitionSubtitle')}</p>
          </div>
        </div>
        <span className={SOURCE_BADGE}>{t('source')}</span>
      </div>

      {/* Active contracts */}
      <section className="mb-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5" />
          {t('contracts')}
        </h3>
        {data.contracts.length === 0 ? (
          <p className="text-sm text-slate-400">{t('noContracts')}</p>
        ) : (
          <ul className="space-y-2">
            {data.contracts.map((c, idx) => (
              <li
                key={c.id || idx}
                className="rounded-lg border border-slate-200 p-3 flex items-start justify-between gap-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900">
                    {(c.product || '').toUpperCase()}
                    {c.formula ? <span className="text-slate-500 font-normal"> · {c.formula}</span> : null}
                  </p>
                  {(c.vehicle || c.property) && (
                    <p className="text-xs text-slate-500 truncate">{c.vehicle || c.property}</p>
                  )}
                </div>
                {typeof c.annual_premium === 'number' && (
                  <span className="text-sm font-semibold text-slate-700 shrink-0">
                    {t('premiumPerYear', { amount: c.annual_premium })}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Assigned advisor */}
      {advisor && (advisor.first_name || advisor.last_name) && (
        <section className="mb-5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
            <UserCog className="w-3.5 h-3.5" />
            {t('advisor')}
          </h3>
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  {advisor.first_name} {advisor.last_name}
                </p>
                <p className="text-xs text-slate-500">
                  {advisor.agency}
                  {typeof advisor.experience_years === 'number'
                    ? ` · ${t('experienceYears', { years: advisor.experience_years })}`
                    : ''}
                </p>
              </div>
              {typeof advisor.global_quality_score === 'number' && (
                <span className="text-xs font-medium px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 shrink-0">
                  {t('qualityScore', { score: advisor.global_quality_score })}
                </span>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Next best actions */}
      {data.next_best_actions.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
            <Target className="w-3.5 h-3.5" />
            {t('nextBestActions')}
          </h3>
          <ul className="space-y-2">
            {data.next_best_actions.map((a, idx) => (
              <li key={a.id || idx} className="rounded-lg border border-violet-100 bg-violet-50/40 p-3">
                <p className="text-sm font-medium text-slate-900">{a.label}</p>
                {a.reason && <p className="text-xs text-slate-500 mt-0.5">{a.reason}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
