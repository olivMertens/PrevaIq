import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { PersonaProvider } from '@/lib/PersonaContext';
import { ToastProvider } from '@/lib/ToastProvider';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages, getLocale } from 'next-intl/server';
import { brand } from '@/lib/brand';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: brand.name,
  description: 'Poste de travail intelligent de traitement de documents pour l\'assurance',
  icons: {
    icon: brand.favicon,
    shortcut: brand.favicon,
    apple: brand.favicon,
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body className={inter.className}>
        <NextIntlClientProvider messages={messages} locale={locale}>
          <PersonaProvider>
            <ToastProvider>
              {children}
            </ToastProvider>
          </PersonaProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
