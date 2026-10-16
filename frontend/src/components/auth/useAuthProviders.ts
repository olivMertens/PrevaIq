'use client';

import { useEffect, useState } from 'react';

export type AuthProviders = {
  entraEnabled: boolean;
  localAuthEnabled: boolean;
  loaded: boolean;
  requestEmail: string | null;
};

/** Sign-in options exposed by /api/auth/check (Entra ID, access-request contact). */
export function useAuthProviders(): AuthProviders {
  const [providers, setProviders] = useState<AuthProviders>({
    entraEnabled: false, localAuthEnabled: false, loaded: false, requestEmail: null,
  });
  useEffect(() => {
    fetch('/api/auth/check')
      .then((res) => res.json())
      .then((data) =>
        setProviders({
          entraEnabled: !!data.entraEnabled,
          localAuthEnabled: !!data.localAuthEnabled,
          loaded: true,
          requestEmail: data.requestEmail || null,
        })
      )
      .catch((error: unknown) => {
        console.error('Failed to load authentication providers', error);
        setProviders({ entraEnabled: false, localAuthEnabled: false, loaded: true, requestEmail: null });
      });
  }, []);
  return providers;
}

export function mailtoHref(email: string, subject: string, body: string): string {
  return `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}
