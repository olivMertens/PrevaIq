'use client';

import { useTranslations } from 'next-intl';

export default function LoadingSpinner() {
  const t = useTranslations('common');
  return (
    <div className="flex flex-col items-center justify-center gap-4">
      <div className="animate-spin rounded-full h-12 w-12 border-4 border-slate-200 border-t-blue-600" />
      <p className="text-sm text-slate-500">{t('loadingApplicationData')}</p>
    </div>
  );
}
