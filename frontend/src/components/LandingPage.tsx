'use client';

import { useState, useMemo, useRef, useCallback } from 'react';
import {
  Upload,
  Plus,
  FileText,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Activity,
  TrendingUp,
} from 'lucide-react';
import { usePersona } from '@/lib/PersonaContext';
import { ApplicationListItem } from '@/lib/types';
import { getApplicationDisplayTitle } from '@/lib/applicationDisplay';
import { createApplication, startProcessing, getApplication } from '@/lib/api';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import { useToast } from '@/lib/ToastProvider';
import ProcessingBanner from './landing/ProcessingBanner';
import PriorityQueues from './landing/PriorityQueues';
import ApplicationsList from './landing/ApplicationsList';
import { brand } from '@/lib/brand';

type ProcessingStep = 'idle' | 'uploading' | 'extracting' | 'analyzing' | 'complete' | 'error';

interface LandingPageProps {
  applications: ApplicationListItem[];
  onSelectApp: (appId: string) => void;
  onRefreshApps: () => void;
  loading: boolean;
  username?: string | null;
}

export default function LandingPage({
  applications,
  onSelectApp,
  onRefreshApps,
  loading,
  username,
}: LandingPageProps) {
  const { currentPersona, personaConfig } = usePersona();
  const t = useTranslations('dashboard');
  const { addToast } = useToast();
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [largeDocumentMode, setLargeDocumentMode] = useState(false);
  const [processingStep, setProcessingStep] = useState<ProcessingStep>('idle');
  const [processingMessage, setProcessingMessage] = useState('');
  const [processingAppId, setProcessingAppId] = useState<string | null>(null);
  const pollingRef = useRef<string | null>(null);

  const isAutomotiveClaims = currentPersona === 'automotive_claims';
  const isUnderwritingPersona = currentPersona === 'underwriting';

  const getAcceptedFileTypes = () => {
    const docs = '.pdf,.docx,.xlsx,.pptx,.tiff';
    const images = '.jpg,.jpeg,.jpe,.png,.bmp,.heif,.heic,.gif,.webp';
    const video = '.mp4,.m4v,.mov,.avi,.mkv,.wmv,.flv';
    if (isAutomotiveClaims) return `${docs},${images},${video}`;
    return `${docs},${images}`;
  };

  const getAcceptedMimeTypes = () => {
    const docs = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'image/tiff'];
    const images = ['image/png', 'image/jpeg', 'image/bmp', 'image/heif', 'image/heic', 'image/gif', 'image/webp'];
    const video = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska', 'video/x-ms-wmv', 'video/x-flv'];
    if (isAutomotiveClaims) return [...docs, ...images, ...video];
    return [...docs, ...images];
  };

  // Dashboard stats
  const stats = useMemo(() => {
    const total = applications.length;
    const completed = applications.filter(a => a.status === 'completed' || a.status === 'extracted' || a.status === 'pending_review').length;
    const processing = applications.filter(a => a.processing_status === 'extracting' || a.processing_status === 'analyzing' || a.status === 'extracting' || a.status === 'analyzing').length;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayCount = applications.filter(a => new Date(a.created_at) >= today).length;
    return { total, completed, processing, todayCount };
  }, [applications]);

  // Priority queues
  const queues = useMemo(() => {
    const readyForReview = applications
      .filter(a => (a.status === 'completed' || a.status === 'extracted' || a.status === 'pending_review') && !a.processing_status)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 5);
    const needsAnalysis = applications
      .filter(a => a.processing_status === 'extracting' || a.processing_status === 'analyzing' || a.status === 'extracting' || a.status === 'analyzing')
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    const hasErrors = applications.filter(a => a.status === 'error');
    return { readyForReview, needsAnalysis, hasErrors };
  }, [applications]);

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return t('greetingMorning');
    if (hour < 17) return t('greetingAfternoon');
    return t('greetingEvening');
  };

  const getAppDisplayTitle = getApplicationDisplayTitle;

  // Poll for completion
  const pollForCompletion = useCallback((appId: string) => {
    if (pollingRef.current === appId) return;
    pollingRef.current = appId;
    let pollCount = 0;

    const poll = async () => {
      if (pollingRef.current !== appId) return;
      pollCount++;
      if (pollCount > 300) {
        setProcessingStep('error');
        setProcessingMessage('Processing timed out.');
        pollingRef.current = null;
        return;
      }
      try {
        const status = await getApplication(appId);
        if (status.processing_status === 'extracting') {
          setProcessingStep('extracting');
          setProcessingMessage('Data Agent extracting documents...');
          onRefreshApps();
          setTimeout(poll, 2000);
        } else if (status.processing_status === 'analyzing') {
          setProcessingStep('analyzing');
          setProcessingMessage('Risk Agent analyzing case...');
          onRefreshApps();
          setTimeout(poll, 2000);
        } else if (status.processing_status === 'error') {
          setProcessingStep('error');
          setProcessingMessage(status.processing_error || 'An error occurred.');
          pollingRef.current = null;
          onRefreshApps();
          addToast('error', status.processing_error || 'Erreur lors du traitement');
        } else if (!status.processing_status) {
          setProcessingStep('complete');
          setProcessingMessage('Analysis complete! Opening application...');
          pollingRef.current = null;
          onRefreshApps();
          addToast('success', 'Analyse terminée avec succès');
          setTimeout(() => onSelectApp(appId), 1500);
        }
      } catch {
        setTimeout(poll, 2000);
      }
    };

    setProcessingStep('extracting');
    setProcessingMessage('Data Agent starting extraction...');
    setTimeout(poll, 2000);
  }, [onRefreshApps, onSelectApp]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const files = Array.from(e.dataTransfer.files).filter(f => getAcceptedMimeTypes().includes(f.type));
    if (files.length > 0) handleFiles(files);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files).filter(f => getAcceptedMimeTypes().includes(f.type));
      if (files.length > 0) handleFiles(files);
    }
  };

  const handleFiles = async (files: File[]) => {
    setUploading(true);
    setProcessingStep('uploading');
    setProcessingMessage('Uploading documents...');
    setProcessingAppId(null);
    setError(null);
    try {
      const app = await createApplication(files, undefined, currentPersona);
      setProcessingAppId(app.id);
      await startProcessing(app.id, largeDocumentMode ? 'large_document' : 'standard');
      setUploading(false);
      onRefreshApps();
      pollForCompletion(app.id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create application';
      setError(msg);
      setProcessingStep('error');
      setProcessingMessage(msg);
      setUploading(false);
      addToast('error', msg);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Dashboard Header */}
      <div className="bg-white border-b border-slate-200">
        <div className="mx-auto px-6 lg:px-8 py-8">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
            <div>
              <h1 className="text-2xl font-bold text-slate-900">
                {getGreeting()}{username ? `, ${username.charAt(0).toUpperCase() + username.slice(1).toLowerCase()}` : ''} !
              </h1>
              <p className="text-slate-500 mt-1 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: brand.dotColor }} />
                {t('title')} — {personaConfig.name}
              </p>
            </div>

            <div className="flex items-center gap-3">
              {isUnderwritingPersona && (
                <button type="button" onClick={() => setLargeDocumentMode(!largeDocumentMode)}
                  className={clsx("flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all border",
                    largeDocumentMode ? "" : "bg-white border-slate-200 text-slate-500 hover:border-slate-300"
                  )}
                  style={largeDocumentMode ? { color: brand.primary, backgroundColor: `${brand.primary}0D`, borderColor: `${brand.primary}33` } : undefined}
                  title={t('condenseHelp')}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                  {t('condense')}
                  <span
                    className={clsx("w-2 h-2 rounded-full transition-colors", !largeDocumentMode && "bg-slate-300")}
                    style={largeDocumentMode ? { backgroundColor: brand.primary } : undefined}
                  />
                </button>
              )}
              <label className={clsx("inline-flex items-center justify-center px-5 py-2.5 text-sm font-medium rounded-lg cursor-pointer shadow-sm transition-all text-white hover:shadow-md", uploading && "opacity-50 cursor-not-allowed")}
                style={{ backgroundColor: brand.primary }}>
                {uploading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{t('processing')}</> : <><Plus className="w-4 h-4 mr-2" />{t('uploadDocuments')}</>}
                <input type="file" className="hidden" multiple accept={getAcceptedFileTypes()} onChange={handleFileInput} disabled={uploading} />
              </label>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
            <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
              <div className="flex items-center justify-between"><span className="text-sm text-slate-500">{t('total')}</span><FileText className="w-4 h-4 text-slate-400" /></div>
              <p className="text-2xl font-bold text-slate-900 mt-1">{stats.total}</p>
            </div>
            <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-100">
              <div className="flex items-center justify-between"><span className="text-sm text-emerald-600">{t('completed')}</span><CheckCircle2 className="w-4 h-4 text-emerald-500" /></div>
              <p className="text-2xl font-bold text-emerald-700 mt-1">{stats.completed}</p>
            </div>
            <div className="bg-sky-50 rounded-xl p-4 border border-sky-100">
              <div className="flex items-center justify-between"><span className="text-sm text-sky-600">{t('inProgress')}</span><Activity className="w-4 h-4 text-sky-500" /></div>
              <p className="text-2xl font-bold text-sky-700 mt-1">{stats.processing}</p>
            </div>
            <div className="bg-violet-50 rounded-xl p-4 border border-violet-100">
              <div className="flex items-center justify-between"><span className="text-sm text-violet-600">{t('today')}</span><TrendingUp className="w-4 h-4 text-violet-500" /></div>
              <p className="text-2xl font-bold text-violet-700 mt-1">{stats.todayCount}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Processing Banner */}
      <ProcessingBanner
        step={processingStep}
        message={processingMessage}
        appId={processingAppId}
        onSelectApp={onSelectApp}
        onDismiss={() => { setProcessingStep('idle'); setProcessingMessage(''); setProcessingAppId(null); }}
      />

      {/* Upload Drop Zone */}
      <div className="mx-auto px-6 lg:px-8 pb-6">
        <div className={clsx(
          "rounded-xl border-2 border-dashed p-6 text-center transition-all relative overflow-hidden",
          dragActive ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white hover:border-slate-300"
        )}
          style={dragActive ? { borderColor: brand.primary, backgroundColor: `${brand.primary}0D` } : undefined}
          onDragEnter={handleDrag} onDragLeave={handleDrag} onDragOver={handleDrag} onDrop={handleDrop}>
          {dragActive ? (
            <div className="py-8">
              <Upload className="w-10 h-10 mx-auto mb-3" style={{ color: brand.primary }} />
              <p className="text-lg font-medium" style={{ color: brand.primary }}>{t('dropFilesActive')}</p>
            </div>
          ) : (
            <div className="flex items-center justify-between py-2">
              <div className="flex items-center gap-4">
                <Upload className="w-5 h-5 text-slate-400" />
                <span className="text-slate-500">{t('dropFilesHere')}</span>
                <div className="flex items-center gap-2 border-l border-slate-200 pl-4">
                  <span className="text-xs font-medium text-slate-500">{t('acceptedDocuments')}</span>
                  <span className="text-xs text-slate-400">{'·'}</span>
                  <span className="text-xs font-medium text-slate-500">{t('acceptedImages')}</span>
                  {isAutomotiveClaims && (
                    <><span className="text-xs text-slate-400">{'·'}</span><span className="text-xs font-medium text-slate-500">{t('acceptedVideo')}</span></>
                  )}
                  <span className="text-xs text-slate-400">{'·'}</span>
                  <span className="text-xs text-slate-400">{t('maxFileSize')}</span>
                </div>
              </div>
              {isUnderwritingPersona && (
                <button type="button" onClick={(e) => { e.stopPropagation(); setLargeDocumentMode(!largeDocumentMode); }}
                  className={clsx("flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all border",
                    largeDocumentMode ? "" : "bg-white border-slate-200 text-slate-400 hover:border-slate-300"
                  )}
                  style={largeDocumentMode ? { color: brand.primary, backgroundColor: `${brand.primary}0D`, borderColor: `${brand.primary}33` } : undefined}
                  title={t('condenseHelp')}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                  {t('condense')}
                  <span
                    className={clsx("w-2 h-2 rounded-full transition-colors", !largeDocumentMode && "bg-slate-300")}
                    style={largeDocumentMode ? { backgroundColor: brand.primary } : undefined}
                  />
                </button>
              )}
            </div>
          )}
        </div>
        {error && (
          <div className="mt-4 p-4 bg-rose-50 text-rose-700 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-5 h-5 flex-shrink-0" /><span>{error}</span>
          </div>
        )}
      </div>

      {/* Priority Queues */}
      <PriorityQueues
        readyForReview={queues.readyForReview}
        needsAnalysis={queues.needsAnalysis}
        hasErrors={queues.hasErrors}
        personaPrimaryColor={brand.primary}
        getAppDisplayTitle={getAppDisplayTitle}
        onSelectApp={onSelectApp}
      />

      {/* Applications Table */}
      <ApplicationsList
        applications={applications}
        loading={loading}
        personaPrimaryColor={brand.primary}
        getAppDisplayTitle={getAppDisplayTitle}
        onSelectApp={onSelectApp}
      />
    </div>
  );
}
