'use client';

import { useTranslations } from 'next-intl';
import type { AnalyzerStatus, AnalyzerInfo, FieldSchema } from './types';

interface AnalyzerTabProps {
  analyzerStatus: AnalyzerStatus | null;
  analyzerSchema: FieldSchema | null;
  analyzers: AnalyzerInfo[];
  analyzerLoading: boolean;
  analyzerProcessing: boolean;
  analyzerError: string | null;
  analyzerSuccess: string | null;
  onCreateAnalyzer: (analyzerId?: string, mediaType?: string) => void;
  onDeleteAnalyzer: (analyzerId: string) => void;
}

export default function AnalyzerTab({
  analyzerStatus,
  analyzerSchema,
  analyzers,
  analyzerLoading,
  analyzerProcessing,
  analyzerError,
  analyzerSuccess,
  onCreateAnalyzer,
  onDeleteAnalyzer,
}: AnalyzerTabProps) {
  const t = useTranslations('adminPanel');

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      {/* Analyzer Status */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-xl font-semibold mb-4 text-slate-900">{t('contentUnderstandingAnalyzer')}</h2>

        {analyzerLoading ? (
          <div className="text-center py-8 text-slate-500">{t('loadingAnalyzerStatus')}</div>
        ) : analyzerError ? (
          <div className="p-4 bg-rose-50 text-rose-700 rounded-lg">{analyzerError}</div>
        ) : analyzerStatus ? (
          <div className="space-y-4">
            {analyzerSuccess && <div className="p-3 bg-emerald-50 text-emerald-700 rounded-lg text-sm">{analyzerSuccess}</div>}

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-50 p-4 rounded-lg">
                <div className="text-xs text-slate-500 uppercase mb-1">{t('customAnalyzer')}</div>
                <div className="font-mono text-sm">{analyzerStatus.analyzer_id}</div>
                <span className={`inline-block mt-2 px-2 py-0.5 text-xs rounded-full ${analyzerStatus.exists ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                  {analyzerStatus.exists ? t('exists') : t('notCreated')}
                </span>
              </div>
              <div className="bg-slate-50 p-4 rounded-lg">
                <div className="text-xs text-slate-500 uppercase mb-1">{t('confidenceScoring')}</div>
                <div className="font-medium">{analyzerStatus.confidence_scoring_enabled ? t('enabled') : t('disabled')}</div>
                <div className="text-xs text-slate-500 mt-1">{t('defaultLabel')} {analyzerStatus.default_analyzer_id}</div>
              </div>
              <div className="bg-slate-50 p-4 rounded-lg">
                <div className="text-xs text-slate-500 uppercase mb-1">{t('cuModelConfig')}</div>
                <div className="text-xs text-slate-600">{t('apiVersion')}: <span className="font-mono">{analyzerStatus.api_version || '—'}</span></div>
                <div className="text-xs text-slate-600 mt-1">{t('completionModel')}: <span className="font-mono">{analyzerStatus.completion_deployment || '—'}</span></div>
                <div className="text-xs text-slate-600 mt-1">{t('embeddingModel')}: <span className="font-mono">{analyzerStatus.embedding_deployment || '—'}</span></div>
              </div>
              <div className="bg-slate-50 p-4 rounded-lg">
                <div className="text-xs text-slate-500 uppercase mb-1">{t('markitdownStatus')}</div>
                <div className="font-medium">{analyzerStatus.markitdown?.enabled ? t('enabled') : t('disabled')}</div>
                <div className="text-xs text-slate-500 mt-1">{t('mode')}: {analyzerStatus.markitdown?.mode || '—'}</div>
                <div className="text-xs text-slate-500 mt-1">
                  {t('contentUnderstanding')}: {analyzerStatus.markitdown?.use_content_understanding ? t('enabled') : t('disabled')}
                </div>
              </div>
            </div>

            <div className="flex gap-2 pt-4">
              <button onClick={() => onCreateAnalyzer()} disabled={analyzerProcessing}
                className="flex-1 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                {analyzerProcessing ? t('processing') : analyzerStatus.exists ? t('updateAnalyzer') : t('createAnalyzer')}
              </button>
              {analyzerStatus.exists && analyzerStatus.analyzer_id !== analyzerStatus.default_analyzer_id && (
                <button onClick={() => onDeleteAnalyzer(analyzerStatus.analyzer_id)} disabled={analyzerProcessing}
                  className="px-4 py-2 text-rose-600 border border-rose-300 rounded-lg hover:bg-rose-50 disabled:opacity-50 transition-colors">
                  {t('delete')}
                </button>
              )}
            </div>

            <div className="bg-sky-50 border border-sky-200 rounded-lg p-4 mt-4">
              <h4 className="font-medium text-sky-900 mb-2">💡 {t('aboutAnalyzers')}</h4>
              <p className="text-sm text-sky-800">{t('aboutAnalyzersDesc')}</p>
            </div>

            <div className="border-t pt-4 mt-4">
              <h3 className="font-medium text-slate-900 mb-3">{t('availableAnalyzers')}</h3>
              <ul className="space-y-2">
                {analyzers.map((analyzer) => (
                  <li key={analyzer.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                    <div>
                      <div className="font-mono text-sm">{analyzer.id}</div>
                      <div className="text-xs text-slate-500">
                        {analyzer.type === 'prebuilt' ? t('azurePrebuilt') : t('custom')} • {analyzer.description}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {analyzer.exists ? (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-100 text-emerald-700">{t('ready')}</span>
                      ) : analyzer.type === 'custom' ? (
                        <button onClick={() => onCreateAnalyzer(analyzer.id, analyzer.media_type)} disabled={analyzerProcessing}
                          className="px-3 py-1 text-xs bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                          {analyzerProcessing ? '...' : t('createAnalyzer')}
                        </button>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-slate-200 text-slate-600">{t('notCreated')}</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
      </div>

      {/* Field Schema */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-slate-900">{t('fieldSchema')}</h2>
          {analyzerSchema && <span className="text-sm text-slate-500">{analyzerSchema.field_count} {t('fieldsDefinedCount')}</span>}
        </div>

        {analyzerSchema ? (
          <div className="space-y-4">
            <div className="max-h-[600px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b">
                    <th className="text-left py-2 font-medium text-slate-700">{t('fieldName')}</th>
                    <th className="text-left py-2 font-medium text-slate-700">{t('type')}</th>
                    <th className="text-left py-2 font-medium text-slate-700">{t('confidence')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {Object.entries(analyzerSchema.schema.fields).map(([fieldName, field]) => (
                    <tr key={fieldName} className="hover:bg-slate-50">
                      <td className="py-2">
                        <div className="font-mono text-xs">{fieldName}</div>
                        <div className="text-xs text-slate-500 truncate max-w-xs" title={field.description}>{field.description}</div>
                      </td>
                      <td className="py-2">
                        <span className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded text-xs">{field.type}</span>
                      </td>
                      <td className="py-2">
                        {field.estimateSourceAndConfidence ? <span className="text-emerald-600">✓</span> : <span className="text-slate-400">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <details className="border-t pt-4">
              <summary className="cursor-pointer text-sm text-indigo-600 hover:text-indigo-700">{t('viewRawSchemaJson')}</summary>
              <pre className="mt-2 p-4 bg-slate-900 text-slate-100 rounded-lg overflow-x-auto text-xs max-h-64">
                {JSON.stringify(analyzerSchema.schema, null, 2)}
              </pre>
            </details>
          </div>
        ) : analyzerLoading ? (
          <div className="text-center py-8 text-slate-500">{t('loadingSchema')}</div>
        ) : null}
      </div>
    </div>
  );
}
