import { NextRequest } from 'next/server';
import { adminFrom, forbidden, relay } from '@/lib/admin-session';
import { auroraAdminApi } from '@/lib/aurora-admin';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  if (!adminFrom(request)) return forbidden();
  const path = request.nextUrl.searchParams.get('mode') === 'live' ? '/test?mode=live' : '/test';
  return relay(await auroraAdminApi(request, path, { method: 'POST' }));
}
