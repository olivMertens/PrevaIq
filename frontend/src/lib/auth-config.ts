export function isEntraEnabled(): boolean {
  return !!(process.env.ENTRA_TENANT_ID && process.env.ENTRA_CLIENT_ID && process.env.ENTRA_CLIENT_SECRET);
}

/** Password login is an explicit development-only option, never a hosted fallback. */
export function isLocalAuthEnabled(): boolean {
  return process.env.NODE_ENV === 'development' && process.env.LOCAL_AUTH_ENABLED === 'true';
}

export function isAuthEnabled(): boolean {
  return process.env.NODE_ENV === 'production' || isEntraEnabled() || isLocalAuthEnabled();
}

export function isSessionUsernameAllowed(username: string): boolean {
  if (username.startsWith('entra:') || username.startsWith('entra-admin:')) {
    return isEntraEnabled();
  }
  return isLocalAuthEnabled();
}
