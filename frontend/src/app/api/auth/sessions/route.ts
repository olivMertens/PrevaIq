import { NextRequest, NextResponse } from 'next/server';
import {
  getActiveSessions,
  getActiveCount,
  clearAllSessions,
  removeSessionsByUsername,
} from '@/lib/session-store';
import { isAuthEnabled, isAdminUsername, validateSessionToken } from '@/lib/auth';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json({
    activeCount: getActiveCount(),
    maxConcurrent: 7,
    sessions: getActiveSessions(),
  });
}

// Admin-only "disconnect everyone" (or ?username=<name> for a single account).
// Clears server-side presence so locked-out users can sign back in immediately.
export async function DELETE(request: NextRequest) {
  if (isAuthEnabled()) {
    const token = request.cookies.get('session')?.value;
    const username = token ? validateSessionToken(token) : null;
    if (!isAdminUsername(username)) {
      return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    }
  }

  const target = request.nextUrl.searchParams.get('username');
  if (target) {
    const cleared = removeSessionsByUsername(target);
    return NextResponse.json({ cleared, scope: 'username', username: target });
  }

  const cleared = clearAllSessions();
  return NextResponse.json({ cleared, scope: 'all' });
}
