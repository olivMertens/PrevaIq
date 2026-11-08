'use client';

import { Moon, Sun } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useAppTheme } from '@/lib/ThemeProvider';

export function ThemeToggle({ menu = false }: { menu?: boolean }) {
  const t = useTranslations('auth');
  const { theme, setTheme } = useAppTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  const Icon = next === 'light' ? Sun : Moon;
  const label = t(next === 'light' ? 'useLightTheme' : 'useDarkTheme');
  return (
    <button
      type="button"
      role={menu ? 'menuitem' : undefined}
      aria-label={label}
      onClick={() => setTheme(next)}
      title={label}
      className={menu
        ? 'flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 focus:bg-slate-100'
        : 'rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-slate-700 hover:bg-slate-100'}
    >
      <Icon className="h-4 w-4" aria-hidden />
      {menu && <span>{label}</span>}
    </button>
  );
}

/** Compact access on pages which do not use the account menu (administration and Client 360). */
export default function AppearanceSwitcher() {
  return <ThemeToggle />;
}
