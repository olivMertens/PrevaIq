'use client';

import { useState, useCallback, useEffect } from 'react';
import { getAnalyzerStatus, getAnalyzerSchema, listAnalyzers, createAnalyzer, deleteAnalyzer } from '@/lib/api';
import type { AnalyzerStatus, AnalyzerInfo, FieldSchema } from '@/lib/types';
import { useToast } from '@/lib/ToastProvider';
import { useTranslations } from 'next-intl';

export function useAnalyzerManager(currentPersona: string, isActive: boolean) {
  const { addToast } = useToast();
  const t = useTranslations('admin');
  const [analyzerStatus, setAnalyzerStatus] = useState<AnalyzerStatus | null>(null);
  const [analyzerSchema, setAnalyzerSchema] = useState<FieldSchema | null>(null);
  const [analyzers, setAnalyzers] = useState<AnalyzerInfo[]>([]);
  const [analyzerLoading, setAnalyzerLoading] = useState(false);
  const [analyzerProcessing, setAnalyzerProcessing] = useState(false);
  const [analyzerError, setAnalyzerError] = useState<string | null>(null);
  const [analyzerSuccess, setAnalyzerSuccess] = useState<string | null>(null);

  const loadAnalyzerData = useCallback(async () => {
    setAnalyzerLoading(true);
    setAnalyzerError(null);
    try {
      const [status, schema, list] = await Promise.all([
        getAnalyzerStatus(currentPersona),
        getAnalyzerSchema(currentPersona),
        listAnalyzers(),
      ]);
      setAnalyzerStatus(status);
      setAnalyzerSchema(schema);
      setAnalyzers(list.analyzers);
    } catch (err) {
      setAnalyzerError(err instanceof Error ? err.message : t('analyzerLoadFailed'));
    } finally {
      setAnalyzerLoading(false);
    }
  }, [currentPersona, t]);

  // Load when tab becomes active or schema cleared
  useEffect(() => {
    if (isActive && (!analyzerSchema || !analyzerStatus)) {
      loadAnalyzerData();
    }
  }, [isActive, analyzerSchema, analyzerStatus, loadAnalyzerData]);

  // Reload when persona changes
  useEffect(() => {
    if (isActive) {
      setAnalyzerSchema(null);
    }
  }, [currentPersona]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreateAnalyzer = useCallback(async (analyzerId?: string, mediaType?: string) => {
    setAnalyzerProcessing(true);
    setAnalyzerError(null);
    setAnalyzerSuccess(null);
    try {
      const result = await createAnalyzer(analyzerId, currentPersona, undefined, mediaType);
      setAnalyzerSuccess(t('analyzerCreatedWithId', { id: result.analyzer_id }));
      addToast('success', t('analyzerCreated'));
      await loadAnalyzerData();
      setTimeout(() => setAnalyzerSuccess(null), 5000);
    } catch (err) {
      setAnalyzerError(err instanceof Error ? err.message : t('analyzerCreateFailed'));
    } finally {
      setAnalyzerProcessing(false);
    }
  }, [currentPersona, loadAnalyzerData, t, addToast]);

  const handleDeleteAnalyzer = useCallback(async (analyzerId: string) => {
    // Prevent deletion of prebuilt analyzers
    const analyzer = analyzers.find(a => a.id === analyzerId);
    if (analyzer?.type === 'prebuilt') return;
    if (!confirm(t('deleteAnalyzerConfirm', { id: analyzerId }))) return;
    setAnalyzerProcessing(true);
    setAnalyzerError(null);
    try {
      await deleteAnalyzer(analyzerId);
      setAnalyzerSuccess(t('analyzerDeleted'));
      addToast('info', t('analyzerDeleted'));
      await loadAnalyzerData();
      setTimeout(() => setAnalyzerSuccess(null), 3000);
    } catch (err) {
      setAnalyzerError(err instanceof Error ? err.message : t('analyzerDeleteFailed'));
    } finally {
      setAnalyzerProcessing(false);
    }
  }, [loadAnalyzerData, analyzers, t, addToast]);

  return {
    analyzerStatus,
    analyzerSchema,
    analyzers,
    analyzerLoading,
    analyzerProcessing,
    analyzerError,
    analyzerSuccess,
    handleCreateAnalyzer,
    handleDeleteAnalyzer,
  };
}
