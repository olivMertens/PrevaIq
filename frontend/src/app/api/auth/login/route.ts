import { NextRequest, NextResponse } from 'next/server';
import { findUser, createSessionToken, isLocalAuthEnabled, isAdminUsername } from '@/lib/auth';
import { registerSession } from '@/lib/session-store';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  if (!isLocalAuthEnabled()) {
    return NextResponse.json(
      { error: 'Local password sign-in is disabled. Use Microsoft Entra ID.' },
      { status: 403 }
    );
  }

  try {
    const { username, password } = await request.json();

    if (!username || !password) {
      return NextResponse.json({ error: 'Username and password are required' }, { status: 400 });
    }

    const user = findUser(username);

    if (!user || user.password !== password) {
      return NextResponse.json({ error: 'Invalid credentials' }, { status: 401 });
    }

    // Use the canonical username so casing/whitespace variations map to one
    // session (correct duplicate-session detection and display name).
    const canonicalUsername = user.username;
    const token = createSessionToken(canonicalUsername);

    // Enforce the shared-POC seat cap. Admin accounts are exempt, and the same
    // user re-logging in takes over their own prior session (handled in the
    // store) instead of being rejected with "already connected".
    const result = registerSession(token, canonicalUsername, {
      unlimited: isAdminUsername(canonicalUsername),
    });
    if (result === 'capacity_full') {
      return NextResponse.json({ error: 'capacity_full' }, { status: 429 });
    }

    const isProduction = process.env.NODE_ENV === 'production';

    const response = NextResponse.json({ username: canonicalUsername });
    response.cookies.set('session', token, {
      httpOnly: true,
      secure: isProduction,
      sameSite: 'lax',
      path: '/',
      maxAge: 60 * 60 * 24, // 24 hours
    });

    return response;
  } catch {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }
}
