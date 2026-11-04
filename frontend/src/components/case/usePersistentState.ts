'use client';

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';

// In-memory fallback so a choice still applies when storage is unavailable (privacy mode).
const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener('storage', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', listener);
  };
}

function readChoice(key: string): string | null {
  try {
    return window.localStorage.getItem(key) ?? memory.get(key) ?? null;
  } catch {
    return memory.get(key) ?? null;
  }
}

/**
 * String state persisted in localStorage. The server snapshot is the initial value, so server
 * and client renders match; unknown stored values fall back to the initial value.
 */
export function usePersistentChoice<T extends string>(
  storageKey: string,
  initial: T,
  allowed: readonly T[],
): [T, (value: T) => void] {
  const stored = useSyncExternalStore(subscribe, () => readChoice(storageKey), () => null);
  const value = stored !== null && (allowed as readonly string[]).includes(stored) ? (stored as T) : initial;

  const update = useCallback(
    (next: T) => {
      memory.set(storageKey, next);
      try {
        window.localStorage.setItem(storageKey, next);
      } catch {
        // Storage unavailable: the in-memory value keeps the choice for this session.
      }
      listeners.forEach((listener) => listener());
    },
    [storageKey],
  );

  return [value, update];
}

/**
 * Time of the user's previous visit to this case (epoch ms, null on a first visit).
 * The current visit is recorded immediately, so "new" means new since the last time.
 */
export function usePreviousVisit(caseId: string | undefined): number | null {
  const [previous, setPrevious] = useState<number | null>(null);

  useEffect(() => {
    if (!caseId) return;
    const key = `prevaiq.case.lastSeen.${caseId}`;
    try {
      const stored = Number(window.localStorage.getItem(key));
      // Read the previous visit and record this one in the same step, once per case;
      // storage is only readable after mount.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPrevious(Number.isFinite(stored) && stored > 0 ? stored : null);
      window.localStorage.setItem(key, String(Date.now()));
    } catch {
      setPrevious(null);
    }
  }, [caseId]);

  return previous;
}
