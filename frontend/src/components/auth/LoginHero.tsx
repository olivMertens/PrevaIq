'use client';

import { useTranslations } from 'next-intl';
import { FileSearch, GitBranch, ShieldAlert, ShieldCheck, UserCheck } from 'lucide-react';
import { brand } from '@/lib/brand';

const POINTS = [
  { key: 'splashPoint1', icon: FileSearch },
  { key: 'splashPoint2', icon: GitBranch },
  { key: 'splashPoint3', icon: ShieldCheck },
  { key: 'splashPoint4', icon: UserCheck },
  { key: 'splashPoint5', icon: ShieldAlert },
] as const;

/** Branded splash panel of the sign-in screen. */
export default function LoginHero() {
  const t = useTranslations('auth');
  return (
    <section
      className="relative flex flex-col justify-between overflow-hidden px-8 py-10 text-white lg:px-14 lg:py-14"
      style={{ background: `linear-gradient(145deg, ${brand.primary} 0%, ${brand.gradientEnd} 100%)` }}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full opacity-20 blur-3xl"
        style={{ backgroundColor: brand.secondary }}
      />
      <div className="relative">
        <span className="inline-flex rounded-2xl bg-white px-4 py-3 shadow-lg">
          <img src={brand.logo} alt={brand.logoAlt} className="h-10 w-auto" />
        </span>
        <h1 className="mt-10 max-w-md text-3xl font-semibold leading-tight lg:text-4xl">{t('splashTitle')}</h1>
        <p className="mt-4 max-w-md text-base text-white/80">{t('splashLead')}</p>
      </div>
      <div className="relative mt-10">
        <ul className="space-y-4">
          {POINTS.map(({ key, icon: Icon }) => (
            <li key={key} className="flex items-center gap-3 text-sm text-white/90">
              <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-white/10">
                <Icon className="h-4 w-4" style={{ color: brand.secondary }} />
              </span>
              {t(key)}
            </li>
          ))}
        </ul>
        <p className="mt-5 max-w-lg text-xs leading-relaxed text-white/70">{t('splashFraudNotice')}</p>
      </div>
    </section>
  );
}
