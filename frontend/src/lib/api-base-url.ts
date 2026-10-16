import { NextRequest } from 'next/server';

const LOCAL_API_BASE_URL = 'http://localhost:8000';

export function getApiBaseUrl(request: NextRequest): string {
  const host = request.headers.get('host') || '';

  if (host.includes('.azurecontainerapps.io') && host.startsWith('ca-frontend-')) {
    const apiHost = host.replace(/^ca-frontend-/, 'ca-api-');
    return `https://${apiHost}`;
  }

  return process.env.API_URL || LOCAL_API_BASE_URL;
}
