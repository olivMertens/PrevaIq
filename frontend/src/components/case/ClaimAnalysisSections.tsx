'use client';

import { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { ANALYSIS_SECTIONS } from '@/lib/claimsWorkspace';
import type { DeepDiveTab } from './caseSignals';

export default function ClaimAnalysisSections({
  focus,
  facts,
  renderSection,
}: {
  focus?: DeepDiveTab;
  facts?: React.ReactNode;
  renderSection: (section: (typeof ANALYSIS_SECTIONS)[number]) => React.ReactNode;
}) {
  const t = useTranslations('caseCockpit');
  const refs = useRef<Partial<Record<DeepDiveTab, HTMLElement | null>>>({});
  useEffect(() => {
    if (focus) refs.current[focus]?.scrollIntoView({ block: 'start' });
  }, [focus]);

  return (
    <div className="space-y-4">
      {facts}
      <nav aria-label={t('workspace.analysisSections')} className="flex flex-wrap gap-2">
        {ANALYSIS_SECTIONS.map((section) => (
          <button key={section} type="button" onClick={() => refs.current[section]?.scrollIntoView({ block: 'start', behavior: 'smooth' })}
            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-indigo-800 hover:bg-indigo-50">
            {t(`drawer.tabs.${section}`)}
          </button>
        ))}
      </nav>
      {ANALYSIS_SECTIONS.map((section) => (
        <section key={section} ref={(element) => { refs.current[section] = element; }} aria-labelledby={`claim-analysis-${section}`}
          className="scroll-mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 id={`claim-analysis-${section}`} className="mb-4 text-base font-semibold text-slate-900">{t(`drawer.tabs.${section}`)}</h2>
          {renderSection(section)}
        </section>
      ))}
    </div>
  );
}
