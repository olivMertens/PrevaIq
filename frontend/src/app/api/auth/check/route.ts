import { NextRequest, NextResponse } from 'next/server';
import {
  displayName,
  isAuthEnabled,
  isEntraEnabled,
  isLocalAuthEnabled,
  sessionRole,
  validateSessionToken,
} from '@/lib/auth';
import { touchSession, getActiveCount } from '@/lib/session-store';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const entraEnabled = isEntraEnabled();
  const localAuthEnabled = isLocalAuthEnabled();
  const requestEmail = process.env.ACCESS_REQUEST_EMAIL || null;
  // If no auth configured, return as if authenticated (auth disabled)
  if (!isAuthEnabled()) {
    return NextResponse.json({ authenticated: true, authEnabled: false, entraEnabled, localAuthEnabled, requestEmail, role: 'admin' });
  }

  const token = request.cookies.get('session')?.value;
  const username = token ? validateSessionToken(token) : null;
  if (!token || !username) {
    return NextResponse.json(
      { authenticated: false, authEnabled: true, entraEnabled, localAuthEnabled, requestEmail, activeUsers: getActiveCount() },
      { status: 401 }
    );
  }

  // Keep session alive
  touchSession(token);

  return NextResponse.json({
    authenticated: true,
    authEnabled: true,
    entraEnabled,
    localAuthEnabled,
    requestEmail,
    username: displayName(username),
    role: sessionRole(username),
  });
}
