'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  APIError, getAuroraForecast, getAuroraStatus,
  type AuroraForecast, type AuroraStatus, type AuroraEvidenceContext,
} from '@/lib/api';

interface EvidenceState {
  applicationId: string;
  forecast: AuroraForecast | null;
  context: AuroraEvidenceContext | null;
  status: AuroraStatus | null;
  error: 'statusError' | 'loadError' | null;
}

const EMPTY: EvidenceState = {applicationId: '', forecast: null, context: null, status: null, error: null};

export function useAuroraEvidence(applicationId: string) {
  const [state, setState] = useState<EvidenceState>(EMPTY);
  useEffect(() => {
    let active = true;
    Promise.allSettled([getAuroraStatus(), getAuroraForecast(applicationId)]).then(([status, saved]) => {
      if (!active) return;
      const missing = saved.status === 'rejected' && saved.reason instanceof APIError && saved.reason.status === 404;
      const differentMode = status.status === 'fulfilled' && saved.status === 'fulfilled' &&
        ((status.value.mode === 'demo_simulation') !== (saved.value.result.provenance?.source === 'demo_simulation'));
      setState({
        applicationId,
        status: status.status === 'fulfilled' ? status.value : null,
        forecast: saved.status === 'fulfilled' && !differentMode ? saved.value.result : null,
        context: saved.status === 'fulfilled' && !differentMode ? saved.value.context ?? null : null,
        error: status.status === 'rejected' ? 'statusError'
          : differentMode || (saved.status === 'rejected' && !missing) ? 'loadError' : null,
      });
    });
    return () => { active = false; };
  }, [applicationId]);
  const setForecast = useCallback((forecast: AuroraForecast, context?: AuroraEvidenceContext) => {
    setState((previous) => previous.applicationId === applicationId
      ? {...previous, forecast, context: context ?? null,
        error: previous.error === 'loadError' ? null : previous.error} : previous);
  }, [applicationId]);
  return {...(state.applicationId === applicationId ? state : EMPTY),
    initializing: state.applicationId !== applicationId, setForecast};
}
