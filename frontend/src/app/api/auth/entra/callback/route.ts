import { NextRequest, NextResponse } from 'next/server';
import { ENTRA_ADMIN_PREFIX, ENTRA_PREFIX, createSessionToken, isEntraAdminEmail } from '@/lib/auth';
import { registerSession } from '@/lib/session-store';
import { STATE_COOKIE, accessApi, entraConfig, exchangeCode, publicOrigin } from '@/lib/entra';

export const dynamic = 'force-dynamic';

function redirect(origin: string, path: string): NextResponse {
  const response = NextResponse.redirect(`${origin}${path}`);
  response.cookies.set(STATE_COOKIE, '', { maxAge: 0, path: '/api/auth/entra' });
  return response;
}

export async function GET(request: NextRequest) {
  const cfg = entraConfig();
  const origin = publicOrigin(request);
  if (!cfg) return redirect(origin, '/login');

  const code = request.nextUrl.searchParams.get('code');
  const state = request.nextUrl.searchParams.get('state');
  const cookieState = request.cookies.get(STATE_COOKIE)?.value;
  if (!code || !state || !cookieState || state !== cookieState) {
    return redirect(origin, '/login?error=state');
  }

  const user = await exchangeCode(cfg, origin, code, state).catch(() => null);
  if (!user) return redirect(origin, '/login?error=entra');
  const isAdmin = isEntraAdminEmail(user.email);

  if (!isAdmin) try {
    const statusRes = await accessApi(request, `/status?email=${encodeURIComponent(user.email)}`);
    if (!statusRes.ok) return redirect(origin, '/access?state=error');
    const { status } = (await statusRes.json()) as { status: string | null };

    if (status === 'refused') return redirect(origin, '/access?state=refused');
    if (status !== 'approved') {
      const req = await accessApi(request, '/request', {
        method: 'POST',
        body: { email: user.email, name: user.name },
      });
      return redirect(origin, req.ok ? '/access?state=pending' : '/access?state=error');
    }
  } catch {
    return redirect(origin, '/access?state=error');
  }

  // Approved users get a user-level session; administration stays with admin accounts.
  const username = `${isAdmin ? ENTRA_ADMIN_PREFIX : ENTRA_PREFIX}${user.email}`;
  const token = createSessionToken(username);
  if (registerSession(token, username, { unlimited: isAdmin }) === 'capacity_full') {
    return redirect(origin, '/login?error=capacity');
  }
  const response = redirect(origin, '/');
  response.cookies.set('session', token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24,
  });
  return response;
}
