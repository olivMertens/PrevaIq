export type ApplicationLoadErrorKey = 'storageUnavailable' | 'loadApplicationsFailed';

export function getApplicationLoadErrorKey(error: unknown): ApplicationLoadErrorKey {
  const message =
    typeof error === 'object' && error !== null && 'message' in error
      ? String(error.message)
      : '';
  return /AuthorizationFailure|not authorized to perform this operation/i.test(message)
    ? 'storageUnavailable'
    : 'loadApplicationsFailed';
}

export function compactAuthIdentity(identity: string | null): string | null {
  return identity?.split('@')[0] || identity;
}
