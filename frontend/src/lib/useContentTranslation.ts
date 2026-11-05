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

// The API translates up to 8 items per request, in parallel (MAX_ITEMS_PER_REQUEST in
// app/content_translation.py); longer lists are sent as successive requests.
const MAX_ITEMS_PER_REQUEST = 8;

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

/**
 * Starts the missing translations, in order (the first items come back first), and returns
 * the requests every item still waits for — including requests started by another view.
 */
function requestTranslations(applicationId: string, locale: string, items: TranslatableItem[]): Promise<void>[] {
  const keyOf = (item: TranslatableItem) => itemKey(applicationId, locale, item);
  const todo = items.filter((item) => {
    const key = keyOf(item);
    return !cache.has(key) && !failures.has(key) && !inflight.has(key);
  });
  let previous: Promise<void> = Promise.resolve();
  for (let start = 0; start < todo.length; start += MAX_ITEMS_PER_REQUEST) {
    const chunk = todo.slice(start, start + MAX_ITEMS_PER_REQUEST);
    const request = previous
      .then(() => translateApplicationContent(applicationId, {
        language: locale,
        pages: chunk.filter((item) => item.kind === 'page').map((item) => item.id),
        batches: chunk.filter((item) => item.kind === 'batch').map((item) => item.id),
      }))
      .then((response) => {
        for (const item of chunk) {
          const result = item.kind === 'page'
            ? response.pages.find((page) => page.page_number === item.id)
            : response.batches.find((batch) => batch.batch_num === item.id);
          if (result) cache.set(keyOf(item), result);
          else failures.add(keyOf(item));
        }
      })
      .catch(() => {
        chunk.forEach((item) => failures.add(keyOf(item)));
      })
      .finally(() => {
        chunk.forEach((item) => inflight.delete(keyOf(item)));
      });
    chunk.forEach((item) => inflight.set(keyOf(item), request));
    previous = request;
  }
  return Array.from(new Set(items.map((item) => inflight.get(keyOf(item))).filter((request): request is Promise<void> => !!request)));
}

/**
 * Translations of case content into the UI language, fetched on demand and cached.
 * Callers pass only items whose language differs from the UI language (memoized list), the
 * most urgent first; each translated batch is shown as soon as it arrives.
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
    for (const request of requestTranslations(applicationId, locale, items)) {
      request.then(() => {
        if (active) setVersion((version) => version + 1);
      });
    }
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
