import { NextRequest } from 'next/server';
import { adminFrom, forbidden, relay } from '@/lib/admin-session';
import { auroraAdminApi } from '@/lib/aurora-admin';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  if (!adminFrom(request)) return forbidden();
  return relay(await auroraAdminApi(request, '/test', { method: 'POST' }));
}
