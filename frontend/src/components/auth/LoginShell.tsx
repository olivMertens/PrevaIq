'use client';

import { createContext, useContext, useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import CurrencySwitcher from '@/components/CurrencySwitcher';
import { Moon, Sun } from 'lucide-react';
import styles from './login.module.css';

type LoginTheme = 'light' | 'dark';
const LoginThemeContext = createContext<LoginTheme>('light');
export const useLoginTheme = () => useContext(LoginThemeContext);

/** Appearance is deliberately scoped to login, not the application document. */
export default function LoginShell({ initialTheme, children }: { initialTheme: LoginTheme; children: ReactNode }) {
  const [theme, setTheme] = useState(initialTheme);
  const t = useTranslations('auth');
  const toggleLabel = t(theme === 'dark' ? 'useLightTheme' : 'useDarkTheme');
  const ThemeIcon = theme === 'dark' ? Sun : Moon;

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark';
    document.cookie = `login-theme=${next};path=/login;max-age=31536000;samesite=lax`;
    setTheme(next);
  }

  return (
    <LoginThemeContext.Provider value={theme}>
      <main className={styles.login} data-theme={theme} data-theme-static>
        <div className={styles.top}>
          <LanguageSwitcher variant="login" />
          <CurrencySwitcher variant="login" />
          <button type="button" className={styles.themeButton} onClick={toggleTheme} aria-label={toggleLabel} title={toggleLabel}>
            <ThemeIcon className="h-4 w-4" aria-hidden />
          </button>
        </div>
        {children}
      </main>
    </LoginThemeContext.Provider>
  );
}
