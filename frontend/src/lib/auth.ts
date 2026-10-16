import { createHmac } from 'crypto';
import { isLocalAuthEnabled, isSessionUsernameAllowed } from './auth-config';

export { isAuthEnabled, isEntraEnabled, isLocalAuthEnabled } from './auth-config';

const SESSION_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

/**
 * Scan process.env for AUTH_USER_* keys and parse "username:password" pairs.
 * Splits on the first colon only, so passwords may contain colons.
 */
export function getUsers(): Map<string, string> {
  const users = new Map<string, string>();
  if (!isLocalAuthEnabled()) return users;
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith('AUTH_USER_') && value) {
      const colonIndex = value.indexOf(':');
      if (colonIndex > 0) {
        const username = value.substring(0, colonIndex);
        const password = value.substring(colonIndex + 1);
        users.set(username, password);
      }
    }
  }
  return users;
}

/** Session usernames of Entra users carry this prefix; they never get admin rights. */
export const ENTRA_PREFIX = 'entra:';
/** Entra administrators (prevaiq-admin* accounts or ACCESS_ADMIN_EMAILS). */
export const ENTRA_ADMIN_PREFIX = 'entra-admin:';

export function isEntraAdminEmail(email: string): boolean {
  const admins = (process.env.ACCESS_ADMIN_EMAILS || '')
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  return email.startsWith('prevaiq-admin') || admins.includes(email);
}

export type SessionRole = 'admin' | 'user' | 'entra';

export function sessionRole(username: string): SessionRole {
  if (username.startsWith(ENTRA_PREFIX)) return 'entra';
  return isAdminUsername(username) ? 'admin' : 'user';
}

export function displayName(username: string): string {
  for (const prefix of [ENTRA_PREFIX, ENTRA_ADMIN_PREFIX]) {
    if (username.startsWith(prefix)) return username.slice(prefix.length);
  }
  return username;
}

/**
 * Look up a configured user tolerant of username casing and surrounding
 * whitespace (mobile keyboards auto-capitalize the first letter and copy-paste
 * often adds spaces, which made hard-to-type accounts like `prevaIqUser1` fail).
 * The password is intentionally NOT normalized — it must still match exactly.
 * Returns the canonical username and its stored password, or null if not found.
 */
export function findUser(inputUsername: string): { username: string; password: string } | null {
  if (!inputUsername) return null;
  const target = inputUsername.trim().toLowerCase();
  if (!target) return null;
  for (const [username, password] of getUsers()) {
    if (username.toLowerCase() === target) {
      return { username, password };
    }
  }
  return null;
}

/**
 * Heuristic admin check based on the account name (the only signal available
 * from AUTH_USER_* env pairs). Admin accounts (e.g. groupIqAdmin) are exempt
 * from the concurrent-seat cap and may clear active sessions.
 */
export function isAdminUsername(username: string | null | undefined): boolean {
  if (!username || username.startsWith(ENTRA_PREFIX)) return false;
  return username.startsWith(ENTRA_ADMIN_PREFIX) || username.toLowerCase().includes('admin');
}

function getSecret(): string {
  return process.env.AUTH_SECRET || 'workbenchiq-default-secret-change-me';
}

/**
 * Create an HMAC-signed session token embedding the username and timestamp.
 * Format: <hmac>.<username>.<timestamp>
 */
export function createSessionToken(username: string): string {
  const timestamp = Date.now().toString();
  const payload = `${username}.${timestamp}`;
  const hmac = createHmac('sha256', getSecret()).update(payload).digest('hex');
  return `${hmac}.${payload}`;
}

/**
 * Validate an HMAC-signed session token.
 * Returns the username if valid, or null if invalid/expired.
 */
export function validateSessionToken(token: string): string | null {
  if (!token) return null;

  const parts = token.split('.');
  if (parts.length < 3) return null;

  const receivedHmac = parts[0];
  const username = parts.slice(1, -1).join('.'); // username may contain dots
  if (!isSessionUsernameAllowed(username)) return null;
  const timestamp = parts[parts.length - 1];

  // Verify timestamp is a number
  const ts = parseInt(timestamp, 10);
  if (isNaN(ts)) return null;

  // Check expiration
  if (Date.now() - ts > SESSION_MAX_AGE_MS) return null;

  // Recompute HMAC and compare
  const payload = `${username}.${timestamp}`;
  const expectedHmac = createHmac('sha256', getSecret()).update(payload).digest('hex');

  // Constant-time comparison
  if (receivedHmac.length !== expectedHmac.length) return null;
  let mismatch = 0;
  for (let i = 0; i < receivedHmac.length; i++) {
    mismatch |= receivedHmac.charCodeAt(i) ^ expectedHmac.charCodeAt(i);
  }
  if (mismatch !== 0) return null;

  return username;
}
