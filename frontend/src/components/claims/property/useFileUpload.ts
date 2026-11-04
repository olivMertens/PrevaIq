'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { addFilesToApplication, getApplication } from '@/lib/api';
import type { ApplicationMetadata } from '@/lib/types';

/** Add files to a case, follow extraction progress over SSE, then refresh the case. */
export function useFileUpload(application: ApplicationMetadata | null, onApplicationUpdate?: (app: ApplicationMetadata) => void) {
  const t = useTranslations('claims');
  const [uploading, setUploading] = useState(false);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  useEffect(() => () => { sseRef.current?.close(); }, []);

  const addFiles = useCallback(async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0 || !application) return;
    const appId = application.id;
    const finish = () => {
      setUploading(false);
      setProgressMessage(null);
    };
    setUploading(true);
    setProgressMessage(t('progress.extracting', { total: fileList.length }));
    try {
      await addFilesToApplication(appId, Array.from(fileList), true);
      const apiBase = typeof window !== 'undefined' && (window as unknown as Record<string, string>).__NEXT_PUBLIC_API_URL
        ? (window as unknown as Record<string, string>).__NEXT_PUBLIC_API_URL
        : (process.env.NEXT_PUBLIC_API_URL || '');
      sseRef.current?.close();
      const es = new EventSource(`${apiBase}/api/applications/${appId}/progress`);
      sseRef.current = es;
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.message) setProgressMessage(data.message);
          if (data.status === 'completed' || data.status === 'done' || data.status === 'error') {
            es.close();
            sseRef.current = null;
            finish();
            getApplication(appId).then((updated) => onApplicationUpdate?.(updated)).catch(() => {});
          }
        } catch {
          // Ignore malformed progress events.
        }
      };
      es.onerror = () => {
        // SSE failed: fall back to a single refresh.
        es.close();
        sseRef.current = null;
        setTimeout(async () => {
          try {
            onApplicationUpdate?.(await getApplication(appId));
          } catch {
            // Keep the current view.
          }
          finish();
        }, 5000);
      };
      setTimeout(() => { es.close(); sseRef.current = null; finish(); }, 180000);
    } catch (err) {
      console.error('File upload failed:', err);
      finish();
    }
  }, [application, onApplicationUpdate, t]);

  return { uploading, progressMessage, addFiles };
}
