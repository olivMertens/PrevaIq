import { NextRequest } from 'next/server';

const LOCAL_API_BASE_URL = 'http://localhost:8000';

function isLocalUrl(url: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/i.test(url);
}

/**
 * Resolve the backend URL for server-side proxy calls.
 *
 * The API_URL baked by deploy.ps1 wins, because the API can run in a different
 * Container Apps environment (and DNS domain) than the frontend. Deriving the API
 * host from the frontend host is only a fallback for images built without API_URL.
 */
export function getApiBaseUrl(request: NextRequest): string {
  const configured = process.env.API_URL?.trim().replace(/\/+$/, '');
  if (configured && !isLocalUrl(configured)) {
    return configured;
  }

  const host = request.headers.get('host') || '';
  if (host.includes('.azurecontainerapps.io') && host.startsWith('ca-frontend-')) {
    const apiHost = host.replace(/^ca-frontend-/, 'ca-api-');
    return `https://${apiHost}`;
  }

  return configured || LOCAL_API_BASE_URL;
}
