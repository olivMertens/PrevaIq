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

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: appId } = await params;
  const apiBaseUrl = getApiBaseUrl(request);

  try {
    const body = await request.text();
    const response = await fetch(
      `${apiBaseUrl}/api/applications/${appId}/generate-communication`,
      {
        method: 'POST',
        headers: getHeaders(),
        body,
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        error: `Communication generation failed: ${response.status}`,
      }));
      return NextResponse.json(errorData, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error(`Failed to generate communication for ${appId}:`, error);
    return NextResponse.json(
      { error: 'Failed to generate communication' },
      { status: 500 }
    );
  }
}
