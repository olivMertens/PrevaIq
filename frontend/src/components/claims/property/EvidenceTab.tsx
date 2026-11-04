'use client';

import { useRef } from 'react';
import { Film, FileText, Image as ImageIcon, Loader2, OctagonAlert, CircleCheck, Upload } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ImageFraudResult } from '@/lib/api';

export interface EvidenceDocument {
  source: string;
  type: string;
  summary: string;
  fileType: { label: string; icon: 'pdf' | 'image' | 'video' | 'document' };
  isPolicyRef: boolean;
}

interface EvidenceTabProps {
  items: EvidenceDocument[];
  imageAnalyses: ImageFraudResult[];
  uploading: boolean;
  progressMessage: string | null;
  onAddFiles: (files: FileList | null) => void;
  onOpen: (index: number) => void;
}

function findAnalysis(analyses: ImageFraudResult[], filename: string) {
  return analyses.find((analysis) => analysis.filename === filename || filename.includes(analysis.filename) || analysis.filename.includes(filename));
}

/** Every document and photo, with the photo authenticity verdict written out (no hover-only tooltip). */
export default function EvidenceTab({ items, imageAnalyses, uploading, progressMessage, onAddFiles, onOpen }: EvidenceTabProps) {
  const t = useTranslations('claims');
  const tc = useTranslations('caseCockpit.evidence');
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-slate-600">{tc('documentCount', { count: items.filter((item) => !item.isPolicyRef).length })}</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
          className="hidden"
          onChange={(event) => onAddFiles(event.target.files)}
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-wait disabled:bg-slate-300"
        >
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Upload className="h-4 w-4" aria-hidden />}
          {uploading ? progressMessage || t('documents.processing') : t('documents.addFiles')}
        </button>
      </div>
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
        {items.map((item, index) => {
          const analysis = item.fileType.icon === 'image' ? findAnalysis(imageAnalyses, item.source) : undefined;
          const score = analysis && !analysis.error ? Math.round((analysis.authenticity_score || 0) * 100) : null;
          const TypeIcon = item.fileType.icon === 'image' ? ImageIcon : item.fileType.icon === 'video' ? Film : FileText;
          const indicator = analysis?.manipulation_indicators?.[0];
          return (
            <li key={`${item.source}-${index}`} className="flex items-start gap-3 p-3">
              <TypeIcon className="mt-0.5 h-4 w-4 flex-shrink-0 text-slate-500" aria-hidden />
              <div className="min-w-0 flex-1">
                <button
                  type="button"
                  onClick={() => onOpen(index)}
                  className="max-w-full truncate text-left font-medium text-indigo-700 hover:underline"
                  title={t('documents.viewSource', { source: item.source })}
                >
                  {item.source}
                </button>
                <p className="text-slate-600">{item.type} · {item.summary}</p>
                {score !== null && (
                  <p className={analysis?.is_likely_authentic ? 'text-emerald-800' : 'text-rose-700'}>
                    <span className="inline-flex items-center gap-1 font-medium">
                      {analysis?.is_likely_authentic
                        ? <CircleCheck className="h-4 w-4" aria-hidden />
                        : <OctagonAlert className="h-4 w-4" aria-hidden />}
                      {tc(analysis?.is_likely_authentic ? 'badge.authentic' : 'badge.suspicious', { score })}
                    </span>
                    {indicator && <span className="text-slate-600"> — {indicator.description || indicator.indicator}</span>}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
