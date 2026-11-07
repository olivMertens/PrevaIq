'use client';

import { useCallback, useEffect, useRef } from 'react';
import { APIError } from '@/lib/api';
import { readWorkflowResponse } from '@/lib/workflowStream';
import type { WorkflowEvent } from './types';

export function useWorkflowRequest(applicationId: string) {
  const pending = useRef<AbortController | null>(null);
  const cancel = useCallback(() => {
    pending.current?.abort();
    pending.current = null;
  }, []);
  useEffect(() => cancel, [applicationId, cancel]);

  const run = useCallback(async (workflowId: string, language: string, onEvent: (event: WorkflowEvent) => void) => {
    cancel();
    const controller = new AbortController();
    pending.current = controller;
    let timedOut = false;
    // Context read + parallel agent budget + synthesis budget, with transport overhead.
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 360000);
    try {
      const response = await fetch(`/api/applications/${encodeURIComponent(applicationId)}/workflow/${encodeURIComponent(workflowId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language, stream: true }),
        signal: controller.signal,
      });
      const result = await readWorkflowResponse(response, event => {
        if (pending.current === controller) onEvent(event);
      });
      return pending.current === controller ? result : null;
    } catch (error) {
      if (pending.current !== controller) return null;
      if (timedOut) throw new APIError(504, 'AI_TIMEOUT', { detail: { code: 'AI_TIMEOUT' } });
      throw error;
    } finally {
      clearTimeout(timer);
      if (pending.current === controller) pending.current = null;
    }
  }, [applicationId, cancel]);

  return { run, cancel };
}
