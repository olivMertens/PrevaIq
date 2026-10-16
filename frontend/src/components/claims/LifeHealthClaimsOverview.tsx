'use client';

import { useState } from 'react';
import {
  Stethoscope,
  FileText,
  ExternalLink,
  ListChecks,
  Activity,
  ChevronDown,
  ChevronRight,
  ChevronUp,
} from 'lucide-react';
import type { ApplicationMetadata } from '@/lib/types';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import CitableValue from '../CitableValue';
import ConfidenceIndicator from '../ConfidenceIndicator';
import { FinalDecisionModal, LineItemOverrideModal } from './Modals';
import { FieldWithConfidence } from './lifeHealthHelpers';
import LifeHealthHeaderStrip from './LifeHealthHeaderStrip';
import useLifeHealthData from './useLifeHealthData';
import CommunicationClientPanel from './CommunicationClientPanel';
import { severityFromSentiment } from './sentimentTone';
import { useToast } from '@/lib/ToastProvider';
import { textValue } from '@/lib/applicationDisplay';

interface LifeHealthClaimsOverviewProps {
  application: ApplicationMetadata | null;
}

export default function LifeHealthClaimsOverview({ application }: LifeHealthClaimsOverviewProps) {
  const t = useTranslations('lifeHealth');
  const { addToast } = useToast();
  const [checkedTasks, setCheckedTasks] = useState<number[]>([]);
  const [expandedSection, setExpandedSection] = useState<string>('reason');
  const [activeTab, setActiveTab] = useState<'timeline' | 'documents'>('timeline');
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());
  const [isFinalDecisionModalOpen, setIsFinalDecisionModalOpen] = useState(false);
  const [overrideLineItem, setOverrideLineItem] = useState<any>(null);
  const [lineItemOverrides, setLineItemOverrides] = useState<Record<number, any>>({});
  const [finalDecisionStatus, setFinalDecisionStatus] = useState<string | null>(null);

  const data = useLifeHealthData(application);

  const handleFinalDecisionConfirm = (decision: any) => {
    setFinalDecisionStatus(decision.decision);
    addToast('success', `Décision "${decision.decision}" enregistrée`);
  };

  const handleOverrideConfirm = (override: any) => {
    setLineItemOverrides(prev => ({ ...prev, [override.line]: override }));
    addToast('info', 'Override appliqué sur la ligne');
  };

  const toggleExpand = (idx: number) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(idx)) newExpanded.delete(idx);
    else newExpanded.add(idx);
    setExpandedItems(newExpanded);
  };

  // Apply local overrides to claim lines
  const claimLinesWithOverrides = data.claimLines.map((l: any) => {
    const override = lineItemOverrides[l.line];
    if (override) {
      return { ...l, allowed: override.allowed, decision: override.action, isOverridden: true };
    }
    return { ...l, isOverridden: false };
  });

  const colorClasses: Record<string, string> = {
    orange: 'bg-orange-500', yellow: 'bg-yellow-500', blue: 'bg-blue-500',
    green: 'bg-green-500', purple: 'bg-purple-500', red: 'bg-red-500',
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-slate-100">
      <LifeHealthHeaderStrip application={application} />

      {/* Communication Client — same banner level as other claims views */}
      {application?.id && (
        <div className="mx-4 mt-2">
          <CommunicationClientPanel
            applicationId={application.id}
            insuredName={(() => {
              const ef = application?.extracted_fields || {};
              for (const k of ['NomAssure', 'PatientName', 'NomBeneficiaire']) {
                const v = ef[k];
                const value = textValue(typeof v === 'object' && v !== null && 'value' in v ? (v as { value: unknown }).value : v);
                if (value) return value;
              }
              return '';
            })()}
            claimReference={application?.external_reference || application?.id || ''}
            decisionStatus={finalDecisionStatus === 'approved' ? 'approved' : finalDecisionStatus === 'denied' ? 'denied' : 'pending'}
            boardLabel="Sinistres Santé"
            severity={severityFromSentiment((application as any)?.sentiment_analysis)}
          />
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-auto p-4">
        <div className="min-h-0 flex flex-col gap-4">

          {/* ROW 1: Clinical Notes | Benefits | Tasks */}
          <div className="grid min-h-0 flex-[1_1_35%] grid-cols-12 gap-4">

            {/* Clinical Notes */}
            <div className="col-span-4 bg-white rounded-lg shadow-sm border border-slate-200 flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
                <Stethoscope className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-slate-900 text-sm">{t('clinicalNotes')}</span>
                <span className="ml-auto text-xs text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">AI</span>
              </div>
              <div className="flex-1 overflow-auto p-3 text-sm">
                <div className="space-y-3">
                  <div className="border border-slate-200 rounded cursor-pointer"
                    onClick={() => setExpandedSection(expandedSection === 'reason' ? '' : 'reason')}>
                    <div className="px-3 py-2 flex items-center justify-between hover:bg-slate-50">
                      <span className="font-medium text-slate-900">{t('reasonForVisit')}</span>
                      {expandedSection === 'reason' ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                    </div>
                    {expandedSection === 'reason' && (
                      <div className="px-3 pb-2 text-slate-600 text-xs">
                        <FieldWithConfidence data={data.reasonForVisitData} />
                      </div>
                    )}
                  </div>
                  <div className="border border-slate-200 rounded cursor-pointer"
                    onClick={() => setExpandedSection(expandedSection === 'diagnoses' ? '' : 'diagnoses')}>
                    <div className="px-3 py-2 flex items-center justify-between hover:bg-slate-50">
                      <span className="font-medium text-slate-900">{t('keyDiagnoses')}</span>
                      {expandedSection === 'diagnoses' ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                    </div>
                    {expandedSection === 'diagnoses' && (
                      <div className="px-3 pb-2 space-y-1">
                        {data.keyDiagnoses.parsed?.primary_diagnosis && (
                          <div className="flex items-center gap-2">
                            {(() => {
                              const code = data.keyDiagnoses.parsed.primary_diagnosis.code;
                              const d = data.getDiagnosisCitation(code);
                              return (
                                <div className="flex items-center gap-1.5">
                                  <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 text-xs rounded font-mono">
                                    <CitableValue value={code} citation={d?.citation} />
                                  </span>
                                  {d?.confidence !== undefined && <ConfidenceIndicator confidence={d.confidence} />}
                                </div>
                              );
                            })()}
                            <span className="text-slate-600 text-xs">{data.keyDiagnoses.parsed.primary_diagnosis.description}</span>
                          </div>
                        )}
                        {data.keyDiagnoses.parsed?.secondary_diagnoses?.map((d: any, idx: number) => (
                          <div key={idx} className="flex items-center gap-2">
                            {(() => {
                              const code = d.code;
                              const diagData = data.getDiagnosisCitation(code);
                              return (
                                <div className="flex items-center gap-1.5">
                                  <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 text-xs rounded font-mono">
                                    <CitableValue value={code} citation={diagData?.citation} />
                                  </span>
                                  {diagData?.confidence !== undefined && <ConfidenceIndicator confidence={diagData.confidence} />}
                                </div>
                              );
                            })()}
                            <span className="text-slate-600 text-xs">{d.description}</span>
                          </div>
                        ))}
                        {!data.keyDiagnoses.parsed?.primary_diagnosis && !data.keyDiagnoses.parsed?.secondary_diagnoses && (
                          <div className="text-slate-400 text-xs italic">{t('noDiagnoses')}</div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Benefits & Policy */}
            <div className="col-span-4 bg-white rounded-lg shadow-sm border border-slate-200 flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
                <FileText className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-slate-900 text-sm">{t('benefitsPolicy')}</span>
              </div>
              <div className="flex-1 overflow-auto p-3 text-xs">
                <div className="space-y-2">
                  <div className="flex justify-between items-center"><span className="text-slate-600">{t('eligibility')}</span><FieldWithConfidence data={data.eligibilityData} className="font-medium text-emerald-600" /></div>
                  <div className="flex justify-between items-center"><span className="text-slate-600">{t('network')}</span><FieldWithConfidence data={data.networkData} className="font-medium" /></div>
                  <div className="flex justify-between items-center"><span className="text-slate-600">{t('deductible')}</span><FieldWithConfidence data={data.deductibleData} className="font-medium" /></div>
                  <div className="flex justify-between items-center border-t pt-2 mt-2"><span className="text-slate-600">{t('oopMax')}</span><FieldWithConfidence data={data.oopMaxData} className="font-medium" /></div>
                  <div className="flex justify-between items-center"><span className="text-slate-600">{t('benefitLimits')}</span><FieldWithConfidence data={data.limitsData} className="font-medium text-emerald-600" /></div>
                </div>
              </div>
            </div>

            {/* Tasks */}
            <div className="col-span-4 bg-white rounded-lg shadow-sm border border-slate-200 flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
                <ListChecks className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-slate-900 text-sm">{t('tasks')}</span>
                <span className="ml-auto text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">{data.tasks.length - checkedTasks.length} {t('pending')}</span>
              </div>
              <div className="flex-1 overflow-auto p-3">
                <div className="space-y-2">
                  {data.tasks.map((task, i) => (
                    <label key={i} className="flex items-center gap-2 cursor-pointer text-sm">
                      <input type="checkbox" checked={checkedTasks.includes(i)}
                        onChange={() => setCheckedTasks(prev => prev.includes(i) ? prev.filter(x => x !== i) : [...prev, i])}
                        className="w-3.5 h-3.5 rounded border-slate-300 text-indigo-600" />
                      <span className={clsx('flex-1', checkedTasks.includes(i) ? 'text-slate-400 line-through' : 'text-slate-900')}>{task.task}</span>
                      <span className="text-xs text-slate-400">{task.due}</span>
                    </label>
                  ))}
                </div>
                <button onClick={() => setIsFinalDecisionModalOpen(true)}
                  className={clsx("mt-3 w-full py-2 text-sm font-medium rounded-lg transition-colors",
                    finalDecisionStatus ? "bg-emerald-600 hover:bg-emerald-700 text-white" : "bg-indigo-600 hover:bg-indigo-700 text-white")}>
                  {finalDecisionStatus ? `Decision: ${finalDecisionStatus}` : t('proposeFinalDecision')}
                </button>
              </div>
            </div>
          </div>

          {/* ROW 2: Timeline & Documents */}
          <div className="min-h-0 flex-[1_1_30%] bg-white rounded-lg shadow-sm border border-slate-200 flex flex-col overflow-hidden">
            <div className="px-4 py-2 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-indigo-600" />
                <span className="font-semibold text-slate-900 text-sm">{t('chronologicalOverview')}</span>
              </div>
              <div className="flex gap-1 bg-slate-200 p-0.5 rounded-lg">
                <button onClick={() => setActiveTab('timeline')}
                  className={clsx('px-3 py-1 text-xs font-medium rounded-md transition-all', activeTab === 'timeline' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900')}>
                  {t('timeline')} ({data.timelineEvents.length})
                </button>
                <button onClick={() => setActiveTab('documents')}
                  className={clsx('px-3 py-1 text-xs font-medium rounded-md transition-all', activeTab === 'documents' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900')}>
                  {t('documents')} ({data.documents.length})
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {activeTab === 'timeline' ? (
                data.timelineEvents.length > 0 ? (
                  <div className="relative">
                    <div className="absolute left-12 top-0 bottom-0 w-px bg-slate-200" />
                    <div className="space-y-4">
                      {data.timelineEvents.map((item, idx) => (
                        <div key={idx} className="relative flex gap-4">
                          <div className="w-16 text-right flex-shrink-0 pt-0.5">
                            <div className="text-xs font-medium text-slate-500">{item.date}</div>
                            <div className="text-[10px] text-slate-400">{item.year}</div>
                          </div>
                          <div className={clsx('w-3 h-3 rounded-full flex-shrink-0 mt-1.5 z-10 ring-2 ring-white', colorClasses[item.color])} />
                          <div className="flex-1 min-w-0">
                            <button onClick={() => toggleExpand(idx)} className="flex items-start justify-between w-full text-left group">
                              <div className="min-w-0">
                                <div className="text-sm font-medium text-slate-900 group-hover:text-indigo-700 transition-colors">{item.title}</div>
                                <div className="text-xs text-slate-500 truncate pr-2">{item.description}</div>
                              </div>
                              {item.details && (expandedItems.has(idx) ? <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" /> : <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />)}
                            </button>
                            {expandedItems.has(idx) && item.details && (
                              <div className="mt-2 p-3 bg-slate-50 rounded-lg text-xs text-slate-600 border border-slate-100">
                                <p className="whitespace-pre-wrap">{item.details}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-slate-400">
                    <Activity className="w-8 h-8 mb-2 opacity-20" /><p className="text-sm">{t('noTimelineEvents')}</p>
                  </div>
                )
              ) : (
                <div className="space-y-2">
                  {data.documents.map((doc, i) => (
                    <div key={i} className="flex items-center gap-3 p-2.5 hover:bg-slate-50 rounded-lg border border-transparent hover:border-slate-200 transition-all group cursor-pointer">
                      <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600"><FileText className="w-4 h-4" /></div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-900 truncate">{doc.name}</div>
                        <div className="text-xs text-slate-500">{doc.type}</div>
                      </div>
                      <ExternalLink className="w-4 h-4 text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  ))}
                  {data.documents.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-full text-slate-400 py-8">
                      <FileText className="w-8 h-8 mb-2 opacity-20" /><p className="text-sm">{t('noDocumentsAvailable')}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* ROW 3: Claim Line Evaluation */}
          <div className="flex-[1_1_45%] bg-white rounded-lg shadow-sm border border-slate-200 flex flex-col overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
              <ListChecks className="w-4 h-4 text-indigo-600" />
              <span className="font-semibold text-slate-900 text-sm">{t('claimLineEvaluation')}</span>
              <span className="ml-auto text-xs text-slate-500">{claimLinesWithOverrides.length} {t('lines')}</span>
            </div>
            <div className="flex-1 overflow-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 sticky top-0">
                  <tr className="text-xs text-slate-500">
                    <th className="px-4 py-2 text-left w-12">#</th>
                    <th className="px-4 py-2 text-left w-20">{t('code')}</th>
                    <th className="px-4 py-2 text-left">{t('description')}</th>
                    <th className="px-4 py-2 text-right w-24">{t('billed')}</th>
                    <th className="px-4 py-2 text-right w-24">{t('allowed')}</th>
                    <th className="px-4 py-2 text-center w-24">{t('aiDecision')}</th>
                    <th className="px-4 py-2 text-center w-24">{t('action')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {claimLinesWithOverrides.map((l: any) => (
                    <tr key={l.line} className="hover:bg-slate-50">
                      <td className="px-4 py-2.5 text-slate-600">{l.line}</td>
                      <td className="px-4 py-2.5 font-mono text-slate-700">
                        <div className="flex items-center gap-1.5">
                          <CitableValue value={l.code} citation={l.citation} />
                          {l.confidence !== undefined && <ConfidenceIndicator confidence={l.confidence} />}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-slate-900">{l.desc}</td>
                      <td className="px-4 py-2.5 text-right text-slate-600">{l.billed}</td>
                      <td className="px-4 py-2.5 text-right text-slate-900 font-medium">{l.allowed}</td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={clsx('px-2 py-0.5 rounded text-xs font-medium',
                          l.decision === 'Approve' ? 'bg-emerald-100 text-emerald-700' :
                          l.decision === 'Deny' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'
                        )}>{l.decision}</span>
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <button onClick={() => setOverrideLineItem(l)}
                          className={clsx("px-2 py-1 text-xs rounded hover:bg-opacity-80",
                            l.isOverridden ? "bg-indigo-100 text-indigo-700 font-medium" : "text-indigo-600 hover:bg-indigo-50")}>
                          {l.isOverridden ? t('edit') : t('override')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </div>

      <FinalDecisionModal isOpen={isFinalDecisionModalOpen} onClose={() => setIsFinalDecisionModalOpen(false)}
        initialData={data.llmOutputs.tasks_decisions?.final_decision?.parsed} onConfirm={handleFinalDecisionConfirm} />
      <LineItemOverrideModal isOpen={!!overrideLineItem} onClose={() => setOverrideLineItem(null)}
        lineItem={overrideLineItem} onConfirm={handleOverrideConfirm} />
    </div>
  );
}
