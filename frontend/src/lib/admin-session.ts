import { NextRequest, NextResponse } from 'next/server';
import { isAuthEnabled, sessionRole, validateSessionToken } from '@/lib/auth';

/** Admin username from the session cookie, or null for non-admin sessions. */
export function adminFrom(request: NextRequest): string | null {
  if (!isAuthEnabled()) return 'local-admin';
  const username = validateSessionToken(request.cookies.get('session')?.value || '');
  return username && sessionRole(username) === 'admin' ? username : null;
}

export function forbidden(): NextResponse {
  return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
}

/** Relay a backend JSON response to the browser. */
export async function relay(res: Response): Promise<NextResponse> {
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
