'use client';

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { APP_THEME_COOKIE, type AppTheme } from '@/lib/theme';

interface ThemeContextValue {
  theme: AppTheme;
  setTheme: (theme: AppTheme) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ initialTheme, children }: { initialTheme: AppTheme; children: ReactNode }) {
  const [theme, setCurrentTheme] = useState(initialTheme);
  const setTheme = useCallback((next: AppTheme) => {
    document.cookie = `${APP_THEME_COOKIE}=${next};path=/;max-age=31536000;samesite=lax`;
    document.documentElement.dataset.appTheme = next;
    document.documentElement.style.colorScheme = next;
    setCurrentTheme(next);
  }, []);

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useAppTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useAppTheme must be used within a ThemeProvider');
  return context;
}
