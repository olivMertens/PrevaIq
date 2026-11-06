import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/api-base-url';

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (process.env.API_KEY) {
    headers['X-API-Key'] = process.env.API_KEY;
  }
  return headers;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: appId } = await params;
  const apiBaseUrl = getApiBaseUrl(request);
  
  try {
    // Forward the query (e.g. ?language=de): the API returns the analysis in that language.
    const response = await fetch(`${apiBaseUrl}/api/applications/${appId}${request.nextUrl.search}`, {
      headers: getHeaders(),
      cache: 'no-store',
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({
        error: `Application request failed: ${response.status}`,
      }));
      return NextResponse.json(data, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error(`Failed to fetch application ${appId}:`, error);
    
    return NextResponse.json(
      { error: 'Application service is unavailable' },
      { status: 502 }
    );
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: appId } = await params;
  const apiBaseUrl = getApiBaseUrl(request);
  
  try {
    const response = await fetch(`${apiBaseUrl}/api/applications/${appId}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: `Delete failed: ${response.status}` }));
      return NextResponse.json(errorData, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error(`Failed to delete application ${appId}:`, error);
    return NextResponse.json(
      { error: 'Failed to delete application' },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: appId } = await params;
  const apiBaseUrl = getApiBaseUrl(request);
  
  try {
    const body = await request.text();
    const response = await fetch(`${apiBaseUrl}/api/applications/${appId}`, {
      method: 'PUT',
      headers: getHeaders(),
      body,
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`Failed to update application ${appId}:`, error);
    return NextResponse.json(
      { error: 'Failed to update application' },
      { status: 500 }
    );
  }
}
