export type AppTheme = 'light' | 'dark';
export const APP_THEME_COOKIE = 'app-theme';

export function resolveAppTheme(value?: string): AppTheme {
  return value === 'dark' ? 'dark' : 'light';
}
