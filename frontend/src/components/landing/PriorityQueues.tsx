'use client';

import {
  FileText,
  ChevronRight,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Activity,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { ApplicationListItem } from '@/lib/types';
import StatusBadge from './StatusBadge';

interface PriorityQueuesProps {
  readyForReview: ApplicationListItem[];
  needsAnalysis: ApplicationListItem[];
  hasErrors: ApplicationListItem[];
  personaPrimaryColor: string;
  getAppDisplayTitle: (app: ApplicationListItem) => string;
  onSelectApp: (appId: string) => void;
}

export default function PriorityQueues({
  readyForReview,
  needsAnalysis,
  hasErrors,
  personaPrimaryColor,
  getAppDisplayTitle,
  onSelectApp,
}: PriorityQueuesProps) {
  const t = useTranslations('dashboard');

  return (
    <div className="mx-auto px-6 lg:px-8 py-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Ready for Review */}
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-emerald-50 to-white">
            <div className="flex items-center justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-900">{t('readyForReview')}</h3>
                  <p className="text-xs text-slate-500">{t('readyForReviewDesc')}</p>
                </div>
              </div>
              <span className="text-2xl font-bold text-emerald-600">{readyForReview.length}</span>
            </div>
          </div>
          <div className="divide-y divide-slate-100">
            {readyForReview.length === 0 ? (
              <div className="px-5 py-8 text-center text-slate-400">
                <CheckCircle2 className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">{t('noReviewCases')}</p>
              </div>
            ) : (
              readyForReview.map((app) => (
                <button key={app.id} onClick={() => onSelectApp(app.id)}
                  className="w-full px-5 py-3 flex items-center justify-between hover:bg-slate-50 transition-colors text-left group">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${personaPrimaryColor}10` }}>
                      <FileText className="w-4 h-4" style={{ color: personaPrimaryColor }} />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-900 transition-colors">{getAppDisplayTitle(app)}</p>
                      <p className="text-xs text-slate-400">
                        {new Date(app.created_at).toLocaleDateString()} at {new Date(app.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-300 group-hover:translate-x-0.5 transition-all" />
                </button>
              ))
            )}
          </div>
        </div>

        {/* Needs AI Analysis */}
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-sky-50 to-white">
            <div className="flex items-center justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-sky-100 flex items-center justify-center">
                  <Activity className="w-4 h-4 text-sky-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-900">{t('needsAnalysis')}</h3>
                  <p className="text-xs text-slate-500">{t('needsAnalysisDesc')}</p>
                </div>
              </div>
              <span className="text-2xl font-bold text-sky-600">{needsAnalysis.length}</span>
            </div>
          </div>
          <div className="divide-y divide-slate-100">
            {needsAnalysis.length === 0 ? (
              <div className="px-5 py-8 text-center text-slate-400">
                <Activity className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">{t('allAgentsIdle')}</p>
              </div>
            ) : (
              needsAnalysis.slice(0, 5).map((app) => (
                <button key={app.id} onClick={() => onSelectApp(app.id)}
                  className="w-full px-5 py-3 flex items-center justify-between hover:bg-slate-50 transition-colors text-left group">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-sky-50 flex items-center justify-center">
                      <Loader2 className="w-4 h-4 text-sky-500 animate-spin" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-900">{getAppDisplayTitle(app)}</p>
                      <p className="text-xs text-slate-400 flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
                        {(() => {
                          const rawStatus = app.processing_status || app.status;
                          const statusMap: Record<string, string> = {
                            extracted: t('stepExtract'),
                            extracting: t('stepExtract'),
                            analyzing: t('stepAnalyze'),
                            completed: t('stepDone'),
                            pending: t('pending'),
                            error: t('errorLabel'),
                          };
                          return statusMap[rawStatus] || rawStatus;
                        })()}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={app.status} processingStatus={app.processing_status} />
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Errors Alert */}
      {hasErrors.length > 0 && (
        <div className="mt-4 bg-rose-50 border border-rose-200 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0" />
            <div className="flex-1">
              <p className="font-medium text-rose-800">{hasErrors.length} {t('requiresAttention')}</p>
              <p className="text-sm text-rose-600 mt-0.5">{t('errorOccurred')}</p>
            </div>
            <button onClick={() => onSelectApp(hasErrors[0].id)}
              className="px-3 py-1.5 bg-rose-600 text-white text-sm font-medium rounded-lg hover:bg-rose-700 transition-colors">
              {t('review')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
