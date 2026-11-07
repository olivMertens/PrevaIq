'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { ANALYSIS_SECTIONS } from '@/lib/claimsWorkspace';
import type { DeepDiveTab } from './caseSignals';
import CaseTabs from './CaseTabs';

export default function ClaimAnalysisSections({
  focus,
  facts,
  renderSection,
}: {
  focus?: DeepDiveTab;
  facts?: React.ReactNode;
  renderSection: (section: (typeof ANALYSIS_SECTIONS)[number]) => React.ReactNode;
}) {
  return <AnalysisTabs key={focus ?? 'summary'} focus={focus} facts={facts} renderSection={renderSection} />;
}

function AnalysisTabs({focus, facts, renderSection}: {
  focus?: DeepDiveTab;
  facts?: React.ReactNode;
  renderSection: (section: (typeof ANALYSIS_SECTIONS)[number]) => React.ReactNode;
}) {
  const t = useTranslations('caseCockpit');
  const [active, setActive] = useState<(typeof ANALYSIS_SECTIONS)[number]>(
    focus === 'cover' || focus === 'fraud' || focus === 'web' ? focus : 'summary',
  );

  return (
    <div className="space-y-4">
      {facts}
      <CaseTabs idPrefix="claim-analysis" label={t('workspace.analysisSections')}
        tabs={ANALYSIS_SECTIONS.map(id => ({id, label: t(`drawer.tabs.${id}`)}))}
        active={active} onChange={setActive} />
      <section role="tabpanel" id={`claim-analysis-${active}-panel`}
        aria-labelledby={`claim-analysis-${active}-tab`} tabIndex={0}
        className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        {renderSection(active)}
      </section>
    </div>
  );
}
