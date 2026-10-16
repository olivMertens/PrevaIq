'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Clock, ShieldX, TriangleAlert } from 'lucide-react';
import { brand } from '@/lib/brand';
import EntraButton from '@/components/auth/EntraButton';
import { mailtoHref, useAuthProviders } from '@/components/auth/useAuthProviders';

type AccessState = 'pending' | 'refused' | 'error';

const ICONS = { pending: Clock, refused: ShieldX, error: TriangleAlert };

/** Outcome of an Entra ID sign-in without demo access yet. */
export default function AccessPage() {
  const t = useTranslations('access');
  const tAuth = useTranslations('auth');
  const { requestEmail } = useAuthProviders();
  const [state, setState] = useState<AccessState>('pending');

  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get('state');
    if (value === 'refused' || value === 'error') setState(value);
  }, []);

  const Icon = ICONS[state];
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 py-10">
      <section className="w-full max-w-md space-y-5 rounded-2xl border border-slate-200 bg-white p-8 shadow-lg">
        <img src={brand.logo} alt={brand.logoAlt} className="h-10 w-auto" />
        <div className="flex items-start gap-3">
          <span
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl"
            style={{ backgroundColor: `${brand.secondary}1F`, color: brand.primary }}
          >
            <Icon className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-lg font-semibold text-slate-900">{t(`${state}Title`)}</h1>
            <p className="mt-1 text-sm text-slate-600">{t(`${state}Lead`)}</p>
          </div>
        </div>
        <EntraButton label={t('retry')} />
        {requestEmail && (
          <a
            href={mailtoHref(requestEmail, tAuth('requestMailSubject'), tAuth('requestMailBody'))}
            className="flex w-full justify-center rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors hover:bg-slate-50"
            style={{ color: brand.primary, borderColor: `${brand.primary}40` }}
          >
            {t('mail')}
          </a>
        )}
        {requestEmail && (
          <p className="text-center text-sm text-slate-600">
            {t('contactUs')}:{' '}
            <a href={`mailto:${requestEmail}`} className="font-medium underline" style={{ color: brand.primary }}>
              {requestEmail}
            </a>
          </p>
        )}
        <p className="text-xs text-slate-500">{t('userOnly')}</p>
        <Link href="/login" className="block text-center text-sm" style={{ color: brand.primary }}>
          {t('back')}
        </Link>
      </section>
    </main>
  );
}
