import { NextRequest, NextResponse } from 'next/server';
import { removeSession } from '@/lib/session-store';

export async function POST(request: NextRequest) {
  const token = request.cookies.get('session')?.value;
  if (token) {
    removeSession(token);
  }

  const response = NextResponse.json({ success: true });
  response.cookies.set('session', '', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 0,
  });
  return response;
}
