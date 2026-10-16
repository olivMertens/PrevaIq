'use client';

import { useEffect, useState, FormEvent, type CSSProperties } from 'react';
import { useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import LoginHero from '@/components/auth/LoginHero';
import EntraButton from '@/components/auth/EntraButton';
import { mailtoHref, useAuthProviders } from '@/components/auth/useAuthProviders';

const CALLBACK_ERRORS: Record<string, 'errorState' | 'errorEntra' | 'errorCapacity'> = {
  state: 'errorState',
  entra: 'errorEntra',
  capacity: 'errorCapacity',
};

export default function LoginPage() {
  const t = useTranslations('auth');
  const { entraEnabled, localAuthEnabled, loaded, requestEmail } = useAuthProviders();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [capacityFull, setCapacityFull] = useState(false);
  const [alreadyConnected, setAlreadyConnected] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const key = CALLBACK_ERRORS[new URLSearchParams(window.location.search).get('error') || ''];
    if (key) setError(t(key));
  }, [t]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setCapacityFull(false);
    setAlreadyConnected(false);
    setLoading(true);

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });

      if (res.ok) {
        // Hard redirect to force full page reload so TopNav picks up session
        window.location.href = '/';
        return;
      } else if (res.status === 409) {
        setAlreadyConnected(true);
      } else if (res.status === 429) {
        setCapacityFull(true);
      } else {
        const data = await res.json();
        setError(data.error || t('error'));
      }
    } catch {
      setError(t('error'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid min-h-screen bg-slate-50 lg:grid-cols-[1.1fr_1fr]">
      <LoginHero />
      <main className="relative flex items-center justify-center px-6 py-10">
        <div className="absolute right-6 top-6">
          <LanguageSwitcher />
        </div>
      <div className="w-full max-w-sm space-y-5">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900">{brand.name}</h2>
          <p className="text-sm text-slate-500 mt-1">{t('signIn')}</p>
        </div>

        {entraEnabled && (
          <div className="space-y-2">
            <EntraButton label={t('entraButton')} />
            <p className="text-xs text-slate-500">{t('entraHint')}</p>
            {localAuthEnabled && <div className="flex items-center gap-3 pt-2 text-xs uppercase tracking-wide text-slate-400">
              <span className="h-px flex-1 bg-slate-200" />
              {t('or')} · {t('demoAccount')}
              <span className="h-px flex-1 bg-slate-200" />
            </div>}
          </div>
        )}

        {loaded && !entraEnabled && !localAuthEnabled && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {t('unavailable')}
          </div>
        )}

        {(entraEnabled || localAuthEnabled) && (
          <p className="text-xs leading-relaxed text-slate-500">{t('demoAccessNotice')}</p>
        )}

        <div aria-live="polite">
          {alreadyConnected && (
            <div className="bg-orange-50 text-orange-700 text-sm px-4 py-3 rounded-lg border border-orange-200">
              {t('alreadyConnected')}
            </div>
          )}

          {capacityFull && (
            <div className="bg-red-50 text-red-700 text-sm px-4 py-3 rounded-lg border border-red-200">
              {t('capacityFull')}
            </div>
          )}

          {error && !capacityFull && !alreadyConnected && (
            <div className="bg-red-50 text-red-700 text-sm px-4 py-3 rounded-lg border border-red-200">
              {error}
            </div>
          )}
        </div>

        {localAuthEnabled && <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-lg border border-slate-200 p-6 space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-slate-700 mb-1.5">
              {t('username')}
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 transition-colors"
              style={{ '--tw-ring-color': brand.secondary } as CSSProperties}
              placeholder={t('username')}
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1.5">
              {t('password')}
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 transition-colors"
              style={{ '--tw-ring-color': brand.secondary } as CSSProperties}
              placeholder={t('password')}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 text-white text-sm font-medium rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            style={{ backgroundColor: brand.primary, '--tw-ring-color': brand.secondary } as CSSProperties}
          >
            {loading ? t('loggingIn') : t('loginButton')}
          </button>
        </form>}

        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-slate-900">{t('requestTitle')}</h3>
          <p className="mt-1 text-xs text-slate-600">{t('requestLead')}</p>
          {requestEmail && (
            <a
              href={mailtoHref(requestEmail, t('requestMailSubject'), t('requestMailBody'))}
              className="mt-3 inline-flex rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-slate-50"
              style={{ color: brand.primary, borderColor: `${brand.primary}40` }}
            >
              {t('requestButton')}
            </a>
          )}
          {requestEmail && (
            <p className="mt-3 text-xs text-slate-600">
              {t('contactUs')}:{' '}
              <a href={`mailto:${requestEmail}`} className="font-medium underline" style={{ color: brand.primary }}>
                {requestEmail}
              </a>
            </p>
          )}
        </div>
      </div>
      </main>
    </div>
  );
}
