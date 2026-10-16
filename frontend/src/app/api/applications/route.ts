import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/api-base-url';

async function errorResponse(response: Response, fallback: string) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const data = await response.json().catch(() => ({ error: fallback }));
    return NextResponse.json(data, { status: response.status });
  }
  const text = await response.text().catch(() => '');
  return NextResponse.json(
    { error: text.trim() || fallback },
    { status: response.status }
  );
}

export async function GET(request: NextRequest) {
  try {
    // Forward query parameters to backend
    const searchParams = request.nextUrl.searchParams;
    const queryString = searchParams.toString();
    const apiBaseUrl = getApiBaseUrl(request);
    const url = queryString 
      ? `${apiBaseUrl}/api/applications?${queryString}`
      : `${apiBaseUrl}/api/applications`;
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (process.env.API_KEY) {
      headers['X-API-Key'] = process.env.API_KEY;
    }

    const response = await fetch(url, {
      headers,
      cache: 'no-store',
    });

    if (!response.ok) {
      return errorResponse(response, `API error: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Failed to fetch applications:', error);
    
    // Return demo data for development
    return NextResponse.json([
      {
        id: '3c0452c0',
        created_at: '2025-11-25T17:40:26Z',
        external_reference: 'UW-004',
        status: 'completed',
        summary_title: 'Mike Johnson - APS Review',
      },
    ]);
  }
}

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    
    const postHeaders: Record<string, string> = {};
    if (process.env.API_KEY) {
      postHeaders['X-API-Key'] = process.env.API_KEY;
    }

    const response = await fetch(`${getApiBaseUrl(request)}/api/applications`, {
      method: 'POST',
      headers: postHeaders,
      body: formData,
    });

    if (!response.ok) {
      return errorResponse(response, `Application creation failed: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Failed to create application:', error);
    const message = error instanceof Error && error.message.trim()
      ? error.message
      : 'Failed to create application';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
