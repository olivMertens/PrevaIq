import { NextRequest } from 'next/server';
import { adminFrom, forbidden, relay } from '@/lib/admin-session';
import { accessApi } from '@/lib/entra';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  if (!adminFrom(request)) return forbidden();
  return relay(await accessApi(request, ''));
}

/** Pre-authorize an e-mail address. */
export async function POST(request: NextRequest) {
  const admin = adminFrom(request);
  if (!admin) return forbidden();
  const { email } = (await request.json().catch(() => ({}))) as { email?: string };
  return relay(await accessApi(request, '/authorize', { method: 'POST', body: { email, admin } }));
}
