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

export function useDocumentProcessing(currentPersona: string) {
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
      setError(err instanceof Error ? err.message : 'Failed to load applications');
    } finally {
      setLoading(false);
    }
  }, [currentPersona]);

  // Load applications on mount and when persona changes
  useEffect(() => {
    loadApplications();
  }, [loadApplications]);

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
        setProcessing({ step: 'error', message: 'Processing timed out.', appId });
        pollingAppIdRef.current = null;
        return;
      }

      try {
        const status = await getApplication(appId);

        if (status.processing_status === 'extracting') {
          setProcessing({ step: 'extracting', message: 'Data Agent extracting documents...', appId });
          setTimeout(poll, pollInterval);
        } else if (status.processing_status === 'analyzing') {
          setProcessing({ step: 'analyzing', message: 'Risk Agent analyzing case...', appId });
          setTimeout(poll, pollInterval);
        } else if (status.processing_status === 'error') {
          setProcessing({ step: 'error', message: status.processing_error || 'Agent encountered an error', appId });
          pollingAppIdRef.current = null;
          await loadApplications();
        } else if (!status.processing_status) {
          setProcessing({ step: 'complete', message: 'All agents complete!', appId });
          pollingAppIdRef.current = null;
          await loadApplications();
          setTimeout(() => setProcessing({ step: 'idle', message: '' }), 3000);
        }
      } catch {
        setTimeout(poll, pollInterval);
      }
    };

    setProcessing({ step: 'extracting', message: 'Reconnecting to agents...', appId });
    setTimeout(poll, pollInterval);
  }, [loadApplications]);

  const handleUploadAndProcess = useCallback(async (
    files: File[],
    externalRef: string,
    useLargeDocMode: 'auto' | 'on' | 'off',
  ) => {
    if (files.length === 0) return;

    try {
      setProcessing({ step: 'uploading', message: 'Uploading files...' });
      const app = await createApplication(files, externalRef || undefined, currentPersona);

      const processingMode = useLargeDocMode === 'on' ? 'large_document'
        : useLargeDocMode === 'off' ? 'standard'
        : undefined;
      await startProcessing(app.id, processingMode);
      pollForProcessingCompletion(app.id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Processing failed';
      setProcessing({ step: 'error', message: msg });
      throw err; // let caller handle toast
    }
  }, [currentPersona, pollForProcessingCompletion]);

  const handleReprocess = useCallback(async (
    appId: string,
    step: 'extract' | 'analyze' | 'prompts-only',
    sections?: string[],
  ) => {
    try {
      if (step === 'extract') {
        setProcessing({ step: 'extracting', message: 'Data Agent starting extraction...', appId });
        await startProcessing(appId);
      } else if (step === 'prompts-only') {
        setProcessing({
          step: 'analyzing',
          message: sections?.length ? `Analysis Agent running: ${sections.join(', ')}...` : 'Analysis Agents running all skills...',
          appId,
        });
        await runUnderwritingAnalysis(appId, sections, true);
      } else {
        setProcessing({ step: 'analyzing', message: 'Risk Agent starting analysis...', appId });
        await runUnderwritingAnalysis(appId, undefined, true);
      }
      pollForProcessingCompletion(appId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Reprocessing failed';
      setProcessing({ step: 'error', message: msg });
      throw err;
    }
  }, [pollForProcessingCompletion]);

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
