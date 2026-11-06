import type { NextRequest } from 'next/server';
import { getApiBaseUrl } from '@/lib/api-base-url';

export async function auroraAdminApi(
  request: NextRequest,
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (process.env.API_KEY) headers['X-API-Key'] = process.env.API_KEY;
  return fetch(`${getApiBaseUrl(request)}/api/internal/aurora${path}`, {
    method: init.method || 'GET',
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: 'no-store',
    signal: AbortSignal.timeout(path === '/test' ? 120_000 : 25_000),
  });
}
