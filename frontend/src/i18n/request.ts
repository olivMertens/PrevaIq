import { getRequestConfig } from 'next-intl/server';
import { cookies } from 'next/headers';
import { swissGermanMessages } from './locales';

const SUPPORTED_LOCALES = ['en', 'fr', 'de', 'de-CH'] as const;
type Locale = (typeof SUPPORTED_LOCALES)[number];

function mergeMessages(
  fallback: Record<string, unknown>,
  overrides: Record<string, unknown>
): Record<string, unknown> {
  const merged = { ...fallback };
  for (const [key, value] of Object.entries(overrides)) {
    const fallbackValue = fallback[key];
    merged[key] =
      value &&
      fallbackValue &&
      typeof value === 'object' &&
      typeof fallbackValue === 'object' &&
      !Array.isArray(value) &&
      !Array.isArray(fallbackValue)
        ? mergeMessages(
            fallbackValue as Record<string, unknown>,
            value as Record<string, unknown>
          )
        : value;
  }
  return merged;
}

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get('locale')?.value;
  const locale: Locale =
    cookieLocale && SUPPORTED_LOCALES.includes(cookieLocale as Locale)
      ? (cookieLocale as Locale)
      : 'en';

  const messageLocale = locale === 'de-CH' ? 'de' : locale;
  const localeMessages = (await import(`../../messages/${messageLocale}.json`)).default;
  const messages =
    locale === 'en'
      ? localeMessages
      : mergeMessages(
          (await import('../../messages/en.json')).default,
          localeMessages
        );

  return {
    locale,
    messages: locale === 'de-CH' ? swissGermanMessages(messages) : messages,
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
