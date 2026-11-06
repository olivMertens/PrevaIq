'use client';

import { Check, Moon, Sun } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useAppTheme } from '@/lib/ThemeProvider';

export function AppearanceOptions({ menu = false }: { menu?: boolean }) {
  const t = useTranslations('appearance');
  const { theme, setTheme } = useAppTheme();
  return (
    <div role="group" aria-label={t('title')} className={menu ? '' : 'flex gap-1'}>
      {(['light', 'dark'] as const).map(option => {
        const Icon = option === 'light' ? Sun : Moon;
        const selected = theme === option;
        return (
          <button
            key={option}
            type="button"
            role={menu ? 'menuitemradio' : undefined}
            aria-checked={menu ? selected : undefined}
            aria-pressed={menu ? undefined : selected}
            onClick={() => setTheme(option)}
            title={t(option)}
            className={menu
              ? 'flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 focus:bg-slate-100'
              : 'rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-100 aria-pressed:bg-slate-100'}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {menu && <span className="flex-1">{t(option)}</span>}
            {!menu && <span className="sr-only">{t(option)}</span>}
            {menu && selected && <Check className="h-4 w-4 text-indigo-600" aria-hidden />}
          </button>
        );
      })}
    </div>
  );
}

/** Compact access on pages which do not use the account menu (administration and Client 360). */
export default function AppearanceSwitcher() {
  const t = useTranslations('appearance');
  return (
    <details className="relative">
      <summary className="cursor-pointer rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700">
        {t('title')}
      </summary>
      <div className="absolute right-0 top-full z-[70] mt-2 rounded-lg border border-slate-200 bg-white p-2 shadow-xl">
        <AppearanceOptions />
      </div>
    </details>
  );
}
