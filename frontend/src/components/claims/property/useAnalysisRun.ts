'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { getApplication, runSentimentAnalysis, runUnderwritingAnalysis } from '@/lib/api';
import type { ApplicationMetadata } from '@/lib/types';

type Update = ((app: ApplicationMetadata) => void) | undefined;

/** AI analysis lifecycle (launch, poll until done, resume after reload) and sentiment auto-run. */
export function useAnalysisRun(application: ApplicationMetadata | null, onApplicationUpdate: Update, autoSentiment = true) {
  const t = useTranslations('claims');
  const locale = useLocale();
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback((appId: string) => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = setInterval(async () => {
      try {
        const app = await getApplication(appId);
        if (app.processing_status !== 'analyzing') {
          if (pollingRef.current) clearInterval(pollingRef.current);
          pollingRef.current = null;
          if (app.processing_error) setError(app.processing_error);
          else onApplicationUpdate?.(app);
          setAnalyzing(false);
        }
      } catch {
        // Ignore transient polling errors.
      }
    }, 3000);
  }, [onApplicationUpdate]);

  useEffect(() => () => { if (pollingRef.current) clearInterval(pollingRef.current); }, []);

  // Resume polling if the application is already analyzing (e.g. page refresh).
  useEffect(() => {
    if (application?.processing_status === 'analyzing' && !pollingRef.current && !analyzing && application.id) {
      setAnalyzing(true);
      poll(application.id);
    }
  }, [application?.processing_status, application?.id, analyzing, poll]);

  // Sentiment agent runs once the analysis exists but no sentiment has been computed.
  const hasAnalysis = !!application?.llm_outputs && Object.keys(application.llm_outputs).length > 0;
  const hasSentiment = !!application?.sentiment_analysis;
  useEffect(() => {
    if (!autoSentiment || !application?.id || analyzing || !hasAnalysis || hasSentiment) return;
    runSentimentAnalysis(application.id)
      .then((result) => {
        if (result && onApplicationUpdate) getApplication(application.id).then(onApplicationUpdate).catch(() => {});
      })
      .catch(() => {});
  }, [application?.id, analyzing, hasAnalysis, hasSentiment, onApplicationUpdate, autoSentiment]);

  const launch = useCallback(async (): Promise<boolean> => {
    if (!application) return false;
    setLoading(true);
    setError(null);
    try {
      await runUnderwritingAnalysis(application.id, undefined, true, locale);
      setAnalyzing(true);
      poll(application.id);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : t('analysisFailed'));
      return false;
    } finally {
      setLoading(false);
    }
  }, [application, locale, poll, t]);

  return { loading, analyzing, error, setError, launch };
}
