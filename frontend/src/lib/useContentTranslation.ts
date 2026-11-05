'use client';

import { useEffect, useState } from 'react';
import { translateApplicationContent, type TranslatedContent } from '@/lib/api';

export interface TranslatableItem {
  kind: 'page' | 'batch';
  id: number;
  text: string;
}

export interface TranslationState {
  content: TranslatedContent | null;
  loading: boolean;
  failed: boolean;
}

// Shared by every view of the session: going back to a page never asks the API again.
const cache = new Map<string, TranslatedContent>();
const failures = new Set<string>();
const inflight = new Map<string, Promise<void>>();

function textHash(text: string): number {
  let hash = 5381;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) + hash + text.charCodeAt(index)) | 0;
  }
  return hash >>> 0;
}

function itemKey(applicationId: string, locale: string, item: TranslatableItem): string {
  return `${applicationId}|${locale}|${item.kind}|${item.id}|${item.text.length}|${textHash(item.text)}`;
}

function requestTranslations(applicationId: string, locale: string, items: TranslatableItem[]): Promise<void> {
  const keyOf = (item: TranslatableItem) => itemKey(applicationId, locale, item);
  const todo = items.filter((item) => {
    const key = keyOf(item);
    return !cache.has(key) && !failures.has(key) && !inflight.has(key);
  });
  if (todo.length > 0) {
    const request = translateApplicationContent(applicationId, {
      language: locale,
      pages: todo.filter((item) => item.kind === 'page').map((item) => item.id),
      batches: todo.filter((item) => item.kind === 'batch').map((item) => item.id),
    })
      .then((response) => {
        for (const item of todo) {
          const result = item.kind === 'page'
            ? response.pages.find((page) => page.page_number === item.id)
            : response.batches.find((batch) => batch.batch_num === item.id);
          if (result) cache.set(keyOf(item), result);
          else failures.add(keyOf(item));
        }
      })
      .catch(() => {
        todo.forEach((item) => failures.add(keyOf(item)));
      })
      .finally(() => {
        todo.forEach((item) => inflight.delete(keyOf(item)));
      });
    todo.forEach((item) => inflight.set(keyOf(item), request));
  }
  return Promise.all(items.map((item) => inflight.get(keyOf(item))).filter(Boolean)).then(() => undefined);
}

/**
 * Translations of case content into the UI language, fetched on demand and cached.
 * Callers pass only items whose language differs from the UI language (memoized list).
 */
export function useContentTranslation(
  applicationId: string,
  locale: string,
  items: TranslatableItem[],
): (item: TranslatableItem) => TranslationState {
  const [, setVersion] = useState(0);

  useEffect(() => {
    if (!applicationId || items.length === 0) return;
    let active = true;
    requestTranslations(applicationId, locale, items).then(() => {
      if (active) setVersion((version) => version + 1);
    });
    return () => {
      active = false;
    };
  }, [applicationId, locale, items]);

  return (item: TranslatableItem) => {
    const key = itemKey(applicationId, locale, item);
    const content = cache.get(key) ?? null;
    const failed = failures.has(key) || Boolean(content?.error);
    return { content, loading: !content && !failed, failed };
  };
}
