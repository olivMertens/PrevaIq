'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ChevronLeft, ChevronRight, Download, ExternalLink, FileQuestion, ZoomIn, ZoomOut } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { getMediaUrl } from '@/lib/api';
import type { CaseDocument } from '@/lib/documentFiles';
import { previewUrl } from '@/lib/media';
import type { MarkdownPage } from '@/lib/types';
import { KIND_ICON } from './DocumentNavigator';
import EmailView from './EmailView';

interface DocumentViewerProps {
  applicationId: string;
  document: CaseDocument<MarkdownPage>;
  /** Page shown, 0-based within the document. */
  pageIndex: number;
  hasPrevious: boolean;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  /** Opens another file of the case (e-mail attachments). */
  onOpenFile: (fileName: string) => void;
}

/** The original document: PDF page, photo, e-mail as a mail client shows it, or a download. */
export default function DocumentViewer({
  applicationId,
  document,
  pageIndex,
  hasPrevious,
  hasNext,
  onPrevious,
  onNext,
  onOpenFile,
}: DocumentViewerProps) {
  const t = useTranslations('pdfViewer');
  const tv = useTranslations('documentViewer');
  const [zoom, setZoom] = useState(100);
  const [failedFile, setFailedFile] = useState<string | null>(null);
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const zoomable = document.kind === 'pdf' || document.kind === 'image';
  const Icon = KIND_ICON[document.kind];

  const fileUrl = useMemo(
    () => getMediaUrl(`/api/applications/${applicationId}/files/${encodeURIComponent(document.file)}`),
    [applicationId, document.file],
  );
  // The PDF viewer opens at the page of the document being read.
  const pdfUrl = `${fileUrl}#page=${pageIndex + 1}&toolbar=1&navpanes=0&view=FitH`;
  const loadError = failedFile === document.file;

  useEffect(() => {
    if (!zoomable) return;
    const handler = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (event.key === '+' || event.key === '=') setZoom((value) => Math.min(value + 25, 200));
      if (event.key === '-') setZoom((value) => Math.max(value - 25, 50));
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [zoomable]);

  const unavailable = (
    <div className="mt-8 max-w-sm rounded-lg bg-white p-8 text-center shadow">
      <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-amber-500" aria-hidden />
      <h4 className="mb-1 text-sm font-semibold text-gray-900">{t('previewUnavailable')}</h4>
      <p className="mb-4 text-xs text-gray-500">{t('inlineUnavailable')}</p>
      <a href={fileUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700">
        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
        {t('openFullPdf')}
      </a>
    </div>
  );

  let content: React.ReactNode;
  if (document.kind === 'email') {
    content = <EmailView key={document.file} applicationId={applicationId} fileName={document.file} fileUrl={fileUrl} onOpenFile={onOpenFile} />;
  } else if (document.kind === 'other') {
    content = (
      <div className="mt-8 max-w-sm rounded-lg bg-white p-8 text-center shadow">
        <FileQuestion className="mx-auto mb-3 h-10 w-10 text-slate-400" aria-hidden />
        <h4 className="mb-1 text-sm font-semibold text-gray-900">{tv('noPreview')}</h4>
        <p className="mb-4 text-xs text-gray-500">{tv('noPreviewHint')}</p>
        <a href={fileUrl} download={document.name} className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700">
          <Download className="h-3.5 w-3.5" aria-hidden />
          {tv('download')}
        </a>
      </div>
    );
  } else if (loadError) {
    content = unavailable;
  } else if (document.kind === 'image') {
    content = (
      <div className="flex items-center justify-center overflow-hidden rounded-lg bg-white p-4 shadow" style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          key={document.file}
          src={previewUrl(fileUrl, 'screen')}
          alt={document.name}
          decoding="async"
          className="max-h-[75vh] max-w-full rounded object-contain"
          onError={() => setFailedFile(document.file)}
        />
      </div>
    );
  } else {
    content = (
      <div className="relative h-full w-full overflow-hidden rounded-lg bg-white shadow" style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}>
        {loadedSrc !== pdfUrl && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-gray-50">
            <div className="text-center">
              <div className="mx-auto mb-2 h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-indigo-500" aria-hidden />
              <p className="text-xs text-gray-500">{t('loadingPdf')}</p>
            </div>
          </div>
        )}
        <iframe
          key={pdfUrl}
          src={pdfUrl}
          className="h-full min-h-[600px] w-full border-0"
          onLoad={() => setLoadedSrc(pdfUrl)}
          onError={() => setFailedFile(document.file)}
          title={t('previewTitle', { file: document.name, page: pageIndex + 1 })}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-slate-100">
      <div className="flex items-center gap-2 border-b border-gray-200 bg-white px-3 py-2">
        <Icon className="h-4 w-4 flex-shrink-0 text-slate-400" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800" title={document.name}>
          {document.name}
        </span>
        {zoomable && (
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setZoom((value) => Math.max(value - 25, 50))} className="rounded p-1.5 text-gray-500 transition-colors hover:bg-gray-100" title={t('zoomOut')} aria-label={t('zoomOut')}>
              <ZoomOut className="h-4 w-4" aria-hidden />
            </button>
            <span className="min-w-[3rem] text-center text-xs text-gray-500">{zoom}%</span>
            <button type="button" onClick={() => setZoom((value) => Math.min(value + 25, 200))} className="rounded p-1.5 text-gray-500 transition-colors hover:bg-gray-100" title={t('zoomIn')} aria-label={t('zoomIn')}>
              <ZoomIn className="h-4 w-4" aria-hidden />
            </button>
          </div>
        )}
        {zoomable ? (
          <a href={fileUrl} target="_blank" rel="noopener noreferrer" className="flex flex-shrink-0 items-center gap-1 text-xs text-gray-500 transition-colors hover:text-indigo-600" title={t('openInNewTab')}>
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            <span className="hidden sm:inline">{t('newTab')}</span>
          </a>
        ) : (
          <a href={fileUrl} download={document.name} className="flex flex-shrink-0 items-center gap-1 text-xs text-gray-500 transition-colors hover:text-indigo-600" title={tv('download')}>
            <Download className="h-3.5 w-3.5" aria-hidden />
            <span className="hidden sm:inline">{tv('download')}</span>
          </a>
        )}
      </div>

      <div className="flex flex-1 items-start justify-center overflow-auto p-2">{content}</div>

      <div className="flex items-center justify-center gap-3 border-t border-gray-200 bg-white px-3 py-2">
        <button type="button" onClick={onPrevious} disabled={!hasPrevious} className="flex items-center gap-1 rounded bg-gray-100 px-2 py-1 text-xs transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-40">
          <ChevronLeft className="h-3 w-3" aria-hidden />
          {t('previous')}
        </button>
        {document.pages.length > 1 && (
          <span className="text-xs tabular-nums text-gray-500">{t('pageOf', { page: pageIndex + 1, total: document.pages.length })}</span>
        )}
        <button type="button" onClick={onNext} disabled={!hasNext} className="flex items-center gap-1 rounded bg-gray-100 px-2 py-1 text-xs transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-40">
          {t('next')}
          <ChevronRight className="h-3 w-3" aria-hidden />
        </button>
      </div>
    </div>
  );
}
