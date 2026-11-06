import { NextRequest } from 'next/server';
import { adminFrom, forbidden, relay } from '@/lib/admin-session';
import { auroraAdminApi } from '@/lib/aurora-admin';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  if (!adminFrom(request)) return forbidden();
  return relay(await auroraAdminApi(request, ''));
}

export async function PUT(request: NextRequest) {
  const admin = adminFrom(request);
  if (!admin) return forbidden();
  const body = await request.json().catch(() => ({}));
  return relay(
    await auroraAdminApi(request, '', {
      method: 'PUT',
      body: { ...(body as object), admin },
    }),
  );
}
