const SESSION_ABSOLUTE_MAX_AGE_MS = 24 * 60 * 60 * 1000; // hard cap from login time
const SESSION_IDLE_TIMEOUT_MS = 30 * 60 * 1000; // evict sessions idle for 30 min
const MAX_CONCURRENT_SESSIONS = 7;

type SessionRecord = {
  username: string;
  createdAt: number;
  lastSeenAt: number;
};

export type ActiveSession = {
  username: string;
  createdAt: string;
  lastSeenAt: string;
  expiresAt: string;
};

export type RegisterSessionResult = 'registered' | 'capacity_full';

const sessionGlobal = globalThis as typeof globalThis & {
  __workbenchiqSessions?: Map<string, SessionRecord>;
};

const sessions = sessionGlobal.__workbenchiqSessions ?? new Map<string, SessionRecord>();
sessionGlobal.__workbenchiqSessions = sessions;

function effectiveExpiry(session: SessionRecord): number {
  return Math.min(
    session.createdAt + SESSION_ABSOLUTE_MAX_AGE_MS,
    session.lastSeenAt + SESSION_IDLE_TIMEOUT_MS
  );
}

// Remove sessions that hit the absolute age cap or went idle past the timeout.
// Idle eviction frees seats held by abandoned sessions (browser closed without
// signing out) that otherwise lingered for the full 24h and blocked re-login.
function cleanupExpiredSessions(now = Date.now()): void {
  for (const [token, session] of sessions.entries()) {
    if (now >= effectiveExpiry(session)) {
      sessions.delete(token);
    }
  }
}

export function registerSession(
  token: string,
  username: string,
  options: { unlimited?: boolean } = {}
): RegisterSessionResult {
  cleanupExpiredSessions();

  // Self-takeover: drop any prior session for the same user (under a different
  // token) so re-logging in always succeeds and keeps a single live session
  // ("last login wins"). This is what stops a stale, never-signed-out record
  // from locking the real user out with "already connected".
  for (const [existingToken, session] of sessions.entries()) {
    if (existingToken !== token && session.username === username) {
      sessions.delete(existingToken);
    }
  }

  // Seat cap protects the shared POC; admin accounts are exempt so an operator
  // can always sign in (e.g. to clear sessions).
  if (!options.unlimited && !sessions.has(token) && sessions.size >= MAX_CONCURRENT_SESSIONS) {
    return 'capacity_full';
  }

  const now = Date.now();
  sessions.set(token, {
    username,
    createdAt: now,
    lastSeenAt: now,
  });
  return 'registered';
}

export function touchSession(token: string): boolean {
  cleanupExpiredSessions();

  const session = sessions.get(token);
  if (!session) {
    return false;
  }

  session.lastSeenAt = Date.now();
  return true;
}

export function removeSession(token: string): boolean {
  return sessions.delete(token);
}

export function removeSessionsByUsername(username: string): number {
  let removed = 0;
  for (const [token, session] of sessions.entries()) {
    if (session.username === username) {
      sessions.delete(token);
      removed += 1;
    }
  }
  return removed;
}

export function clearAllSessions(): number {
  const count = sessions.size;
  sessions.clear();
  return count;
}

export function getActiveCount(): number {
  cleanupExpiredSessions();
  return sessions.size;
}

export function getActiveSessions(): ActiveSession[] {
  cleanupExpiredSessions();

  return Array.from(sessions.values()).map((session) => ({
    username: session.username,
    createdAt: new Date(session.createdAt).toISOString(),
    lastSeenAt: new Date(session.lastSeenAt).toISOString(),
    expiresAt: new Date(effectiveExpiry(session)).toISOString(),
  }));
}
