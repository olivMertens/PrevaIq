/** Microsoft four-square mark + label, linking to the Entra ID sign-in route. */
export default function EntraButton({ label }: { label: string }) {
  return (
    // Full navigation to the OIDC redirect route: <Link> would prefetch it.
    // eslint-disable-next-line @next/next/no-html-link-for-pages
    <a
      href="/api/auth/entra/login"
      className="flex w-full items-center justify-center gap-3 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 shadow-sm transition-colors hover:bg-slate-50"
    >
      <svg width="18" height="18" viewBox="0 0 21 21" aria-hidden>
        <rect x="1" y="1" width="9" height="9" fill="#f25022" />
        <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
        <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
        <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
      </svg>
      {label}
    </a>
  );
}
