import { NextRequest, NextResponse } from 'next/server';
import { isAuthEnabled, isSessionUsernameAllowed } from './lib/auth-config';

const SESSION_MAX_AGE_MS = 24 * 60 * 60 * 1000;

async function validateSessionToken(token: string): Promise<string | null> {
  if (!token) return null;

  const secret = process.env.AUTH_SECRET || 'workbenchiq-default-secret-change-me';
  const parts = token.split('.');
  if (parts.length < 3) return null;

  const receivedHmac = parts[0];
  const username = parts.slice(1, -1).join('.');
  if (!isSessionUsernameAllowed(username)) return null;
  const timestamp = parts[parts.length - 1];
  const ts = parseInt(timestamp, 10);
  if (isNaN(ts)) return null;
  if (Date.now() - ts > SESSION_MAX_AGE_MS) return null;

  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign(
    'HMAC', key, encoder.encode(`${username}.${timestamp}`)
  );
  const expectedHmac = Array.from(new Uint8Array(signature))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
  if (receivedHmac.length !== expectedHmac.length) return null;
  let mismatch = 0;
  for (let index = 0; index < receivedHmac.length; index++) {
    mismatch |= receivedHmac.charCodeAt(index) ^ expectedHmac.charCodeAt(index);
  }
  return mismatch === 0 ? username : null;
}

export async function proxy(request: NextRequest) {
  if (!isAuthEnabled()) return NextResponse.next();

  const { pathname } = request.nextUrl;
  if (
    pathname === '/login' ||
    pathname === '/access' ||
    pathname.startsWith('/api/auth/') ||
    pathname === '/api/health' ||
    pathname.startsWith('/_next/') ||
    pathname.startsWith('/favicon') ||
    pathname.endsWith('.ico') ||
    pathname.endsWith('.png') ||
    pathname.endsWith('.svg') ||
    pathname.endsWith('.jpg') ||
    pathname.endsWith('.css') ||
    pathname.endsWith('.js')
  ) {
    return NextResponse.next();
  }

  const token = request.cookies.get('session')?.value;
  if (!token) return NextResponse.redirect(new URL('/login', request.url));
  const username = await validateSessionToken(token);
  if (!username) {
    const response = NextResponse.redirect(new URL('/login', request.url));
    response.cookies.set('session', '', { maxAge: 0, path: '/' });
    return response;
  }
  // Entra-approved users get the user demo only: administration stays reserved.
  if (username.startsWith('entra:') && (pathname === '/admin' || pathname.startsWith('/admin/'))) {
    return NextResponse.redirect(new URL('/', request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};