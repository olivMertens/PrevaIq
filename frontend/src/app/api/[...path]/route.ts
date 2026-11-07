import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/api-base-url';

/**
 * Catch-all API route that proxies unhandled requests to the backend.
 * This ensures all /api/* requests are forwarded to the Python backend.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, (await params).path);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, (await params).path, 'POST');
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, (await params).path, 'PUT');
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, (await params).path, 'DELETE');
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, (await params).path, 'PATCH');
}

const CACHE_HEADERS = ['cache-control', 'etag', 'last-modified'];
const BINARY_HEADERS = [
  ...CACHE_HEADERS,
  'content-length',
  'content-disposition',
  'accept-ranges',
  'content-range',
  'x-content-type-options',
];

function pickHeaders(response: Response, names: string[]): Record<string, string> {
  const picked: Record<string, string> = {};
  for (const name of names) {
    const value = response.headers.get(name);
    if (value) picked[name] = value;
  }
  return picked;
}

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method?: string
) {
  try {
    const path = pathSegments.join('/');
    const searchParams = request.nextUrl.searchParams;
    const queryString = searchParams.toString();
    const apiBaseUrl = getApiBaseUrl(request);
    const url = queryString
      ? `${apiBaseUrl}/api/${path}?${queryString}`
      : `${apiBaseUrl}/api/${path}`;

    // Internal endpoints (access requests) are server-to-server only. Check the
    // normalized URL so dot segments cannot reach them.
    if (new URL(url).pathname.toLowerCase().startsWith('/api/internal')) {
      return NextResponse.json({ error: 'Not found' }, { status: 404 });
    }

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    // Inject API key for backend authentication (server-side only, never exposed to browser)
    const apiKey = process.env.API_KEY;
    if (apiKey) {
      (headers as Record<string, string>)['X-API-Key'] = apiKey;
    }

    // Forward Range header for video/audio streaming (HTTP 206 Partial Content)
    const rangeHeader = request.headers.get('range');
    if (rangeHeader) {
      (headers as Record<string, string>)['Range'] = rangeHeader;
    }

    // Conditional requests let the browser reuse a cached file (HTTP 304, no body)
    const ifNoneMatch = request.headers.get('if-none-match');
    if (ifNoneMatch) {
      (headers as Record<string, string>)['If-None-Match'] = ifNoneMatch;
    }

    const fetchOptions: RequestInit = {
      method: method || request.method,
      headers,
      cache: 'no-store',
      signal: request.signal,
    };

    // Forward body for non-GET requests
    if (method && method !== 'GET') {
      try {
        const contentType = request.headers.get('content-type') || '';
        if (contentType.includes('multipart/form-data')) {
          // For form data, forward as-is
          const formData = await request.formData();
          delete (headers as Record<string, string>)['Content-Type'];
          fetchOptions.body = formData;
        } else {
          // For JSON, forward body
          const body = await request.text();
          if (body) {
            fetchOptions.body = body;
          }
        }
      } catch {
        // No body to forward
      }
    }

    const response = await fetch(url, fetchOptions);

    if (response.status === 304) {
      return new NextResponse(null, { status: 304, headers: pickHeaders(response, CACHE_HEADERS) });
    }

    // Handle non-JSON responses
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/event-stream')) {
      return new NextResponse(response.body, {
        status: response.status,
        headers: {
          'Content-Type': contentType,
          'Cache-Control': 'no-cache, no-transform',
          'X-Accel-Buffering': 'no',
        },
      });
    } else if (contentType.includes('application/json')) {
      const data = await response.json();
      return NextResponse.json(data, { status: response.status });
    } else {
      // Binary content (PDFs, images, video) is streamed as-is: never decoded as text
      // (which corrupts PDFs) and never buffered, so the first bytes reach the browser
      // while the rest is still downloading.
      const isBinary = /^(application\/(pdf|octet-stream)|image\/|video\/|audio\/)/.test(contentType);
      if (isBinary) {
        const binaryHeaders = pickHeaders(response, BINARY_HEADERS);
        // fetch() decodes compressed bodies, so an upstream length would no longer match.
        if (response.headers.get('content-encoding')) delete binaryHeaders['content-length'];
        return new NextResponse(response.body, {
          status: response.status,
          headers: { 'Content-Type': contentType, ...binaryHeaders },
        });
      }
      const text = await response.text();
      return new NextResponse(text, {
        status: response.status,
        headers: { 'Content-Type': contentType },
      });
    }
  } catch (error) {
    console.error('API proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to proxy request to backend' },
      { status: 500 }
    );
  }
}
