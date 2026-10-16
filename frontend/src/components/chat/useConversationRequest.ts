'use client';

import { useCallback, useEffect, useRef } from 'react';
import { APIError, sendConversation, type ConversationRequest } from '@/lib/api';

export function useConversationRequest(applicationId: string) {
  const pending = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    pending.current?.abort();
    pending.current = null;
  }, []);

  useEffect(() => cancel, [applicationId, cancel]);

  const send = useCallback(async (body: ConversationRequest) => {
    cancel();
    const controller = new AbortController();
    pending.current = controller;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 120000);
    try {
      const result = await sendConversation(applicationId, body, controller.signal);
      return pending.current === controller ? result : null;
    } catch (error) {
      if (pending.current !== controller) return null;
      if (timedOut) {
        throw new APIError(504, 'AI_TIMEOUT', { detail: { code: 'AI_TIMEOUT' } });
      }
      throw error;
    } finally {
      clearTimeout(timer);
      if (pending.current === controller) pending.current = null;
    }
  }, [applicationId, cancel]);

  return { send, cancel };
}