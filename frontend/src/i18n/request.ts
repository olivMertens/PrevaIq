import { getRequestConfig } from 'next-intl/server';
import { cookies } from 'next/headers';

const SUPPORTED_LOCALES = ['en', 'fr'] as const;
type Locale = (typeof SUPPORTED_LOCALES)[number];

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get('locale')?.value;
  const locale: Locale =
    cookieLocale && SUPPORTED_LOCALES.includes(cookieLocale as Locale)
      ? (cookieLocale as Locale)
      : 'en';

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
    // Gracefully handle missing translation keys instead of crashing React.
    // Dynamic field names from LLM outputs (e.g. formatLabels.contrat,
    // formatLabels.plafond biens mobiliers) generate unpredictable keys.
    onError(error) {
      if (error.code === 'MISSING_MESSAGE') {
        // Expected for dynamic keys — silent (no crash, no console spam)
        return;
      }
      console.error(error);
    },
    getMessageFallback({ key }) {
      // Auto-format the key as a readable label
      return key.replace(/_/g, ' ').replace(/\b[a-z]/g, (c) => c.toUpperCase());
    },
  };
});
