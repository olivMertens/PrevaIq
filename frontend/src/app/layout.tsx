import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { PersonaProvider } from '@/lib/PersonaContext';
import { ToastProvider } from '@/lib/ToastProvider';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages, getLocale } from 'next-intl/server';
import { brand } from '@/lib/brand';
import { cookies } from 'next/headers';
import { ThemeProvider } from '@/lib/ThemeProvider';
import { resolveAppTheme, APP_THEME_COOKIE } from '@/lib/theme';
import { CurrencyProvider } from '@/lib/CurrencyProvider';
import { CURRENCY_COOKIE, resolveReferenceCurrency } from '@/lib/currency';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: brand.name,
  description: 'Poste de travail intelligent de traitement de documents pour l\'assurance',
  icons: {
    icon: { url: brand.favicon, type: 'image/svg+xml', sizes: 'any' },
    shortcut: brand.favicon,
    apple: { url: brand.icon, type: 'image/png', sizes: '240x240' },
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();
  const cookieStore = await cookies();
  const theme = resolveAppTheme(cookieStore.get(APP_THEME_COOKIE)?.value);
  const currency = resolveReferenceCurrency(cookieStore.get(CURRENCY_COOKIE)?.value);

  return (
    <html lang={locale} data-app-theme={theme} style={{ colorScheme: theme }}>
      <body className={inter.className}>
        <NextIntlClientProvider messages={messages} locale={locale}>
          <ThemeProvider initialTheme={theme}>
            <CurrencyProvider initialCurrency={currency}>
              <PersonaProvider>
                <ToastProvider>
                  {children}
                </ToastProvider>
              </PersonaProvider>
            </CurrencyProvider>
          </ThemeProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
