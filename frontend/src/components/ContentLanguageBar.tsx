'use client';

import { Languages, Loader2 } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import type { TranslationState } from '@/lib/useContentTranslation';

export type ContentView = 'translated' | 'original';

const LANGUAGE_KEYS: Record<string, string> = {
  en: 'languageEnglish',
  fr: 'languageFrench',
  de: 'languageGerman',
  'de-CH': 'languageGermanSwiss',
};

interface ContentLanguageBarProps {
  sourceLanguage: string;
  view: ContentView;
  state: TranslationState | null;
  onViewChange: (view: ContentView) => void;
}

/** States which language is shown (machine translation or original) and switches between them. */
export default function ContentLanguageBar({ sourceLanguage, view, state, onViewChange }: ContentLanguageBarProps) {
  const t = useTranslations('common.contentLanguage');
  const tLanguages = useTranslations('auth');
  const locale = useLocale();
  const name = (code: string) => (LANGUAGE_KEYS[code] ? tLanguages(LANGUAGE_KEYS[code]) : code.toUpperCase());
  const source = name(sourceLanguage);

  let message: string;
  if (view === 'original') message = t('original', { language: source });
  else if (state?.failed) message = t('failed', { language: source });
  else if (state?.loading || !state?.content) message = t('translating', { language: source });
  else message = t('translatedFrom', { language: source });

  const busy = view === 'translated' && !state?.failed && (state?.loading || !state?.content);

  return (
    <div className="flex items-center justify-between gap-3 border-b border-indigo-100 bg-indigo-50/60 px-4 py-1.5 text-xs text-indigo-900">
      <p role="status" aria-live="polite" className="flex min-w-0 items-center gap-1.5">
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" aria-hidden />
        ) : (
          <Languages className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />
        )}
        <span className="truncate">{message}</span>
      </p>
      {!(view === 'translated' && state?.failed) && (
        <button
          type="button"
          onClick={() => onViewChange(view === 'translated' ? 'original' : 'translated')}
          className="flex-shrink-0 font-medium text-indigo-700 underline-offset-2 hover:underline"
        >
          {view === 'translated' ? t('showOriginal') : t('showTranslation', { language: name(locale) })}
        </button>
      )}
    </div>
  );
}
