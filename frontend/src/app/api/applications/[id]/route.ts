import { NextRequest, NextResponse } from 'next/server';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
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
    const response = await fetch(`${apiBaseUrl}/api/applications/${appId}`, {
      headers: getHeaders(),
      cache: 'no-store',
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error(`Failed to fetch application ${appId}:`, error);
    
    // Try to load from local data directory for demo purposes
    try {
      const metadataPath = join(
        process.cwd(),
        '..',
        'data',
        'applications',
        appId,
        'metadata.json'
      );
      
      if (existsSync(metadataPath)) {
        const metadata = JSON.parse(readFileSync(metadataPath, 'utf-8'));
        return NextResponse.json(metadata);
      }
    } catch (localError) {
      console.error('Local data load failed:', localError);
    }

    return NextResponse.json(
      { error: 'Application not found' },
      { status: 404 }
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
