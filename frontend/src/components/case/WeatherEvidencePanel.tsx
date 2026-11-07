'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { getClaimLocation, type ClaimLocation } from '@/lib/api';
import CaseTabs from './CaseTabs';
import LocationCard from './LocationCard';
import AuroraRiskPanel from './AuroraRiskPanel';
import { CockpitCard } from './caseUi';

type WeatherTab = 'aurora' | 'location' | 'web';

export default function WeatherEvidencePanel({
  applicationId, claimDate, webPanel,
}: {applicationId: string; claimDate?: string; webPanel?: React.ReactNode}) {
  const t = useTranslations('caseCockpit.aurora');
  const [active, setActive] = useState<WeatherTab>('aurora');
  const [state, setState] = useState<{id: string; location: ClaimLocation | null; failed: boolean}>({
    id: '', location: null, failed: false,
  });
  useEffect(() => {
    let current = true;
    getClaimLocation(applicationId).then(
      location => { if (current) setState({id: applicationId, location, failed: false}); },
      () => { if (current) setState({id: applicationId, location: null, failed: true}); },
    );
    return () => { current = false; };
  }, [applicationId]);
  const location = state.id === applicationId ? state.location : null;
  const tabs: Array<{id: WeatherTab; label: string}> = [
    {id: 'aurora', label: t('workspace.aurora')},
    {id: 'location', label: t('workspace.location')},
    ...(webPanel ? [{id: 'web' as const, label: t('workspace.web')}] : []),
  ];
  return (
    <div className="space-y-3">
      <CaseTabs tabs={tabs} active={active} onChange={setActive} idPrefix="weather-evidence"
        label={t('workspace.title')} />
      <div role="tabpanel" id={`weather-evidence-${active}-panel`}
        aria-labelledby={`weather-evidence-${active}-tab`} tabIndex={0}>
        {active === 'aurora' && <AuroraRiskPanel key={applicationId} applicationId={applicationId}
          latitude={location?.place?.lat} longitude={location?.place?.lon} claimDate={claimDate} />}
        {active === 'location' && <LocationCard location={location} failed={state.id === applicationId && state.failed} />}
        {active === 'web' && <CockpitCard title={t('workspace.web')} headingId="weather-public-sources">
          <div className="max-h-[32rem] overflow-y-auto p-4">{webPanel}</div>
        </CockpitCard>}
      </div>
    </div>
  );
}
