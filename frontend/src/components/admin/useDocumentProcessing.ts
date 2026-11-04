'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  createApplication,
  deleteApplication,
  listApplications,
  getApplication,
  startProcessing,
  runUnderwritingAnalysis,
} from '@/lib/api';
import type { ApplicationListItem } from '@/lib/types';
import type { ProcessingState } from './types';
import { useLocale, useTranslations } from 'next-intl';

export function useDocumentProcessing(currentPersona: string) {
  const locale = useLocale();
  const t = useTranslations('admin');
  const [applications, setApplications] = useState<ApplicationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState<ProcessingState>({ step: 'idle', message: '' });
  const pollingAppIdRef = useRef<string | null>(null);

  const loadApplications = useCallback(async () => {
    try {
      setLoading(true);
      const apps = await listApplications(currentPersona);
      setApplications(apps);
      setError(null);
    } catch (err) {
      console.error('Failed to load applications', err);
      const message = err instanceof Error ? err.message : '';
      setError(
        /AuthorizationFailure|not authorized to perform this operation/i.test(message)
          ? t('processing.storageUnavailable')
          : t('processing.loadApplicationsFailed')
      );
    } finally {
      setLoading(false);
    }
  }, [currentPersona, t]);

  // Load applications on mount and when persona changes
  useEffect(() => {
    loadApplications();
  }, [loadApplications, t]);

  const pollForProcessingCompletion = useCallback((appId: string) => {
    if (pollingAppIdRef.current === appId) return;
    pollingAppIdRef.current = appId;

    const pollInterval = 2000;
    const maxPolls = 300;
    let pollCount = 0;

    const poll = async () => {
      if (pollingAppIdRef.current !== appId) return;
      pollCount++;
      if (pollCount > maxPolls) {
        setProcessing({ step: 'error', message: t('processing.timedOut'), appId });
        pollingAppIdRef.current = null;
        return;
      }

      try {
        const status = await getApplication(appId, locale);

        if (status.processing_status === 'extracting') {
          setProcessing({ step: 'extracting', message: t('processing.extracting'), appId });
          setTimeout(poll, pollInterval);
        } else if (status.processing_status === 'analyzing') {
          setProcessing({ step: 'analyzing', message: t('processing.analyzing'), appId });
          setTimeout(poll, pollInterval);
        } else if (status.processing_status === 'error') {
          setProcessing({ step: 'error', message: status.processing_error || t('processing.agentError'), appId });
          pollingAppIdRef.current = null;
          await loadApplications();
        } else if (!status.processing_status) {
          setProcessing({ step: 'complete', message: t('processing.complete'), appId });
          pollingAppIdRef.current = null;
          await loadApplications();
          setTimeout(() => setProcessing({ step: 'idle', message: '' }), 3000);
        }
      } catch {
        setTimeout(poll, pollInterval);
      }
    };

    setProcessing({ step: 'extracting', message: t('processing.reconnecting'), appId });
    setTimeout(poll, pollInterval);
  }, [loadApplications, locale, t]);

  const handleUploadAndProcess = useCallback(async (
    files: File[],
    externalRef: string,
    useLargeDocMode: 'auto' | 'on' | 'off',
  ) => {
    if (files.length === 0) return;

    try {
      setProcessing({ step: 'uploading', message: t('processing.uploading') });
      const app = await createApplication(files, externalRef || undefined, currentPersona);

      const processingMode = useLargeDocMode === 'on' ? 'large_document'
        : useLargeDocMode === 'off' ? 'standard'
        : undefined;
      await startProcessing(app.id, processingMode, locale);
      pollForProcessingCompletion(app.id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('processing.failed');
      setProcessing({ step: 'error', message: msg });
      throw err; // let caller handle toast
    }
  }, [currentPersona, locale, pollForProcessingCompletion, t]);

  const handleReprocess = useCallback(async (
    appId: string,
    step: 'extract' | 'analyze' | 'prompts-only',
    sections?: string[],
  ) => {
    try {
      if (step === 'extract') {
        setProcessing({ step: 'extracting', message: t('processing.startingExtraction'), appId });
        await startProcessing(appId, undefined, locale);
      } else if (step === 'prompts-only') {
        setProcessing({
          step: 'analyzing',
          message: sections?.length
            ? t('processing.runningSections', { sections: sections.join(', ') })
            : t('processing.runningAllSkills'),
          appId,
        });
        await runUnderwritingAnalysis(appId, sections, true, locale);
      } else {
        setProcessing({ step: 'analyzing', message: t('processing.startingAnalysis'), appId });
        await runUnderwritingAnalysis(appId, undefined, true, locale);
      }
      pollForProcessingCompletion(appId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('processing.reprocessingFailed');
      setProcessing({ step: 'error', message: msg });
      throw err;
    }
  }, [locale, pollForProcessingCompletion, t]);

  const handleDeleteApp = useCallback(async (appId: string) => {
    await deleteApplication(appId);
    await loadApplications();
  }, [loadApplications]);

  const isProcessing = ['uploading', 'extracting', 'analyzing'].includes(processing.step);

  return {
    applications,
    loading,
    error,
    processing,
    isProcessing,
    setProcessing,
    loadApplications,
    pollForProcessingCompletion,
    handleUploadAndProcess,
    handleReprocess,
    handleDeleteApp,
  };
}
