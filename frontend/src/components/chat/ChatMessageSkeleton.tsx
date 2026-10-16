'use client';

import { Bot } from 'lucide-react';
import { useTranslations } from 'next-intl';

export default function ChatMessageSkeleton() {
  const t = useTranslations('chat');

  return (
    <div className="flex gap-3 justify-start" role="status" aria-live="polite" data-testid="chat-pending">
      <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0" aria-hidden="true">
        <Bot className="w-5 h-5 text-indigo-600" />
      </div>
      <div className="min-w-0 w-72 max-w-[calc(100%-2.75rem)] rounded-lg bg-slate-100 px-4 py-3">
        <span className="text-sm text-slate-600">{t('responsePending')}</span>
        <div className="mt-3 space-y-2 motion-safe:animate-pulse" aria-hidden="true">
          <div className="h-2 w-full rounded bg-slate-200" />
          <div className="h-2 w-5/6 rounded bg-slate-200" />
          <div className="h-2 w-3/5 rounded bg-slate-200" />
        </div>
      </div>
    </div>
  );
}