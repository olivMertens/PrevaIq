import { NextResponse } from 'next/server';
import { isAuthEnabled, isEntraEnabled, isLocalAuthEnabled } from '@/lib/auth';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    commitSha: process.env.NEXT_PUBLIC_COMMIT_SHA || 'unknown',
    auth: {
      enabled: isAuthEnabled(),
      entraEnabled: isEntraEnabled(),
      localAuthEnabled: isLocalAuthEnabled(),
    },
  });
}
