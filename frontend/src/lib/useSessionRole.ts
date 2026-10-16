'use client';

import { useEffect, useState } from 'react';

export type SessionRole = 'admin' | 'user' | 'entra';

/** Role of the signed-in session (null while loading). */
export function useSessionRole(): SessionRole | null {
  const [role, setRole] = useState<SessionRole | null>(null);
  useEffect(() => {
    fetch('/api/auth/check')
      .then((res) => res.json())
      .then((data) => setRole((data.role as SessionRole) || 'user'))
      .catch(() => setRole('user'));
  }, []);
  return role;
}
