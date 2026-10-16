import { createHash, randomBytes } from 'crypto';
import type { NextRequest } from 'next/server';
import { getApiBaseUrl } from '@/lib/api-base-url';

/** Microsoft Entra ID (OIDC authorization code flow) for demo sign-in. */

export const STATE_COOKIE = 'entra_state';
export const CALLBACK_PATH = '/api/auth/entra/callback';

type EntraConfig = { tenantId: string; clientId: string; clientSecret: string };

export type EntraUser = { email: string; name: string | null };

export function entraConfig(): EntraConfig | null {
  const tenantId = process.env.ENTRA_TENANT_ID;
  const clientId = process.env.ENTRA_CLIENT_ID;
  const clientSecret = process.env.ENTRA_CLIENT_SECRET;
  if (!tenantId || !clientId || !clientSecret) return null;
  return { tenantId, clientId, clientSecret };
}

/** Public origin of the frontend (Container Apps terminates TLS in front of Next.js). */
export function publicOrigin(request: NextRequest): string {
  if (process.env.PUBLIC_BASE_URL) return process.env.PUBLIC_BASE_URL.replace(/\/$/, '');
  const host = request.headers.get('x-forwarded-host') || request.headers.get('host') || '';
  const local = host.startsWith('localhost') || host.startsWith('127.0.0.1');
  const proto = request.headers.get('x-forwarded-proto') || (local ? 'http' : 'https');
  return `${proto}://${host}`;
}

/** Random state; the cookie stores it, and its hash is the OIDC nonce. */
export function newState(): string {
  return randomBytes(24).toString('base64url');
}

function nonceFor(state: string): string {
  return createHash('sha256').update(state).digest('base64url');
}

export function authorizeUrl(cfg: EntraConfig, origin: string, state: string): string {
  const url = new URL(`https://login.microsoftonline.com/${cfg.tenantId}/oauth2/v2.0/authorize`);
  url.search = new URLSearchParams({
    client_id: cfg.clientId,
    response_type: 'code',
    redirect_uri: `${origin}${CALLBACK_PATH}`,
    response_mode: 'query',
    scope: 'openid profile email',
    state,
    nonce: nonceFor(state),
    prompt: 'select_account',
  }).toString();
  return url.toString();
}

/**
 * Exchange the code for an ID token. The token comes straight from the Entra
 * token endpoint over TLS with the client secret (OIDC Core 3.1.3.7), so its
 * claims are checked (audience, tenant, nonce, expiry) without JWKS validation.
 */
export async function exchangeCode(
  cfg: EntraConfig, origin: string, code: string, state: string
): Promise<EntraUser | null> {
  const res = await fetch(`https://login.microsoftonline.com/${cfg.tenantId}/oauth2/v2.0/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: cfg.clientId,
      client_secret: cfg.clientSecret,
      grant_type: 'authorization_code',
      code,
      redirect_uri: `${origin}${CALLBACK_PATH}`,
      scope: 'openid profile email',
    }),
    cache: 'no-store',
  });
  if (!res.ok) return null;
  const { id_token: idToken } = (await res.json()) as { id_token?: string };
  const payload = idToken?.split('.')[1];
  if (!payload) return null;
  const claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as Record<string, unknown>;
  // Multi-tenant ("organizations") apps: the issuer carries the user's own tenant.
  const multiTenant = cfg.tenantId === 'organizations' || cfg.tenantId === 'common';
  const issuerTenant = multiTenant ? String(claims.tid || '') : cfg.tenantId;
  const issuer = `https://login.microsoftonline.com/${issuerTenant}/v2.0`;
  const now = Math.floor(Date.now() / 1000);
  if (claims.aud !== cfg.clientId || claims.iss !== issuer || claims.nonce !== nonceFor(state)) return null;
  if (typeof claims.exp !== 'number' || claims.exp < now) return null;
  // preferred_username (UPN) uses a domain verified by the user's tenant; the
  // optional `email` claim is not verified, so it is never used as identity.
  const email = String(claims.preferred_username || '').trim().toLowerCase();
  if (!email.includes('@')) return null;
  return { email, name: typeof claims.name === 'string' ? claims.name : null };
}

/** Server-to-server call to the backend access-request endpoints (API key injected). */
export async function accessApi(
  request: NextRequest, path: string, init: { method?: string; body?: unknown } = {}
): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (process.env.API_KEY) headers['X-API-Key'] = process.env.API_KEY;
  return fetch(`${getApiBaseUrl(request)}/api/internal/access${path}`, {
    method: init.method || 'GET',
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: 'no-store',
  });
}
