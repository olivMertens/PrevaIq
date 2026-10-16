import { NextRequest, NextResponse } from 'next/server';
import { STATE_COOKIE, authorizeUrl, entraConfig, newState, publicOrigin } from '@/lib/entra';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const cfg = entraConfig();
  const origin = publicOrigin(request);
  if (!cfg) return NextResponse.redirect(`${origin}/login`);

  const state = newState();
  const response = NextResponse.redirect(authorizeUrl(cfg, origin, state));
  response.cookies.set(STATE_COOKIE, state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/api/auth/entra',
    maxAge: 10 * 60,
  });
  return response;
}
