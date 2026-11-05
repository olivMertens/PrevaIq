'use client';

import { useEffect, useState } from 'react';

export interface AgentCapabilities {
  /** The Fabric data agent (portfolio statistics) is connected. */
  fabric_data: boolean;
  web_iq: boolean;
}

const UNKNOWN: AgentCapabilities = { fabric_data: false, web_iq: false };
let pending: Promise<AgentCapabilities> | null = null;

function loadCapabilities(): Promise<AgentCapabilities> {
  if (!pending) {
    pending = fetch('/api/agents/status')
      .then((response) => (response.ok ? response.json() : null))
      .then((status) => ({ ...UNKNOWN, ...(status?.capabilities ?? {}) }))
      .catch(() => {
        pending = null; // Retried the next time the panel opens.
        return UNKNOWN;
      });
  }
  return pending;
}

/** Chat capabilities of this environment, fetched once per page when first needed. */
export function useAgentCapabilities(enabled: boolean): AgentCapabilities {
  const [capabilities, setCapabilities] = useState<AgentCapabilities>(UNKNOWN);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    loadCapabilities().then((value) => {
      if (active) setCapabilities(value);
    });
    return () => {
      active = false;
    };
  }, [enabled]);
  return capabilities;
}
