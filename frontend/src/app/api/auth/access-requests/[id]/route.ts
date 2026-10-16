import { NextRequest } from 'next/server';
import { adminFrom, forbidden, relay } from '@/lib/admin-session';
import { accessApi } from '@/lib/entra';

export const dynamic = 'force-dynamic';

/** Approve or refuse (revoke) an access request. */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const admin = adminFrom(request);
  if (!admin) return forbidden();
  const { id } = await params;
  const { decision } = (await request.json().catch(() => ({}))) as { decision?: string };
  return relay(
    await accessApi(request, `/${encodeURIComponent(id)}/decision`, {
      method: 'POST',
      body: { decision, admin },
    })
  );
}
