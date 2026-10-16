/**
 * Automotive Claims Overview Component - Compact Layout
 *
 * Decision bar + fraud panel at top (like Sinistres Habitation),
 * then summary, risk analysis, evidence, damage assessment.
 */

'use client';

import React, { useState, useCallback, useRef } from 'react';
import {
  Car, FileText, AlertTriangle, XCircle,
  Upload, RefreshCw, Shield, Sparkles, RotateCcw,
  Play, Clock, ChevronRight, Eye
} from 'lucide-react';
import VideoTimeline from './VideoTimeline';
import PDFViewer from './PDFViewer';
import DamageViewer from './DamageViewer';
import FraudAnalysisPanel from './FraudAnalysisPanel';
import CommunicationClientPanel from './CommunicationClientPanel';
import { severityFromSentiment } from './sentimentTone';
import CustomerAffiliationBanner from './CustomerAffiliationBanner';
import UnderwritingDecisionFooter from '@/components/UnderwritingDecisionFooter';
import { MediaItem, getMediaUrl, runUnderwritingAnalysis, getApplication } from '@/lib/api';
import type { FraudAnalysisResponse } from '@/lib/api';
import { getApplicationDisplayTitle, textValue } from '@/lib/applicationDisplay';
import useAutomotiveClaimData from './useAutomotiveClaimData';
import { useTranslations, useLocale } from 'next-intl';

interface AutomotiveClaimsOverviewProps {
  applicationId: string;
  displayTitle?: string;
  isLoading?: boolean;
  onApprove?: () => void;
  onAdjust?: () => void;
  onDeny?: () => void;
  onInvestigate?: () => void;
}

// Translation maps for English values returned by the claims engine
const SEVERITY_FR: Record<string, string> = { minor: 'MINEUR', moderate: 'MODÉRÉ', severe: 'SÉVÈRE', heavy: 'GRAVE', total_loss: 'PERTE TOTALE' };
const LOCATION_FR: Record<string, string> = {
  'front': 'Avant', 'rear': 'Arrière', 'left': 'Gauche', 'right': 'Droite', 'roof': 'Toit',
  'front left': 'Avant gauche', 'front right': 'Avant droit', 'rear left': 'Arrière gauche', 'rear right': 'Arrière droit',
  'side left': 'Côté gauche', 'side right': 'Côté droit', 'hood': 'Capot', 'trunk': 'Coffre',
  'bumper': 'Pare-chocs', 'front bumper': 'Pare-chocs avant', 'rear bumper': 'Pare-chocs arrière',
  'windshield': 'Pare-brise', 'door': 'Portière', 'fender': 'Aile', 'quarter panel': 'Aile arrière',
};
const INDICATOR_TYPE_FR: Record<string, string> = {
  'Documentation': 'Documentation', 'Pattern': 'Schéma suspect', 'Behavioral': 'Comportement',
  'Financial': 'Financier', 'Timeline': 'Chronologie', 'general': 'Général',
};
function trFr(map: Record<string, string>, val: string): string {
  const lower = val.toLowerCase().trim();
  return map[lower] || map[val] || val;
}

function getExtractedText(extractedFields: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const direct = extractedFields[key];
    const matched =
      direct ||
      Object.entries(extractedFields).find(([fieldKey]) => fieldKey.endsWith(`:${key}`))?.[1];
    if (matched && typeof matched === 'object' && 'value' in matched) {
      const value = textValue((matched as { value: unknown }).value);
      if (value) return value;
    }
    const value = textValue(matched);
    if (value) return value;
  }
  return '';
}

function trDesc(desc: string): string {
  // Translate common English claim phrases to French
  const map: [RegExp, string][] = [
    [/No police report or accident statement/i, 'Pas de rapport de police ni de constat'],
    [/for a hit-and-run at a public intersection/i, 'pour un délit de fuite sur voie publique'],
    [/No third-party or witness information provided/i, 'Aucune information de tiers ou de témoin fournie'],
    [/Urgency and emotional language in claim communication/i, 'Langage d\'urgence et émotionnel dans la communication'],
    [/Panel Repair or Replace/i, 'Réparation ou remplacement de panneau'],
    [/crack/i, 'fissure'],
    [/dent/i, 'enfoncement'],
    [/scratch/i, 'rayure'],
    [/Repair/i, 'Réparation'],
    [/Replace/i, 'Remplacement'],
  ];
  let result = desc;
  for (const [pattern, replacement] of map) {
    result = result.replace(pattern, replacement);
  }
  return result;
}

export function AutomotiveClaimsOverview({
  applicationId,
  displayTitle,
  isLoading = false,
}: AutomotiveClaimsOverviewProps) {
  const d = useAutomotiveClaimData(applicationId);
  const t = useTranslations('claimsModals');
  const locale = useLocale();

  const [selectedPDF, setSelectedPDF] = useState<MediaItem | null>(null);
  const [selectedImage, setSelectedImage] = useState<MediaItem | null>(null);
  const [showVideoModal, setShowVideoModal] = useState(false);
  const [fraudResult, setFraudResult] = useState<FraudAnalysisResponse | null>(null);
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resolvedDisplayTitle = d.application ? getApplicationDisplayTitle(d.application) : displayTitle;

  const handleFraudComplete = useCallback((result: FraudAnalysisResponse) => {
    setFraudResult(result);
  }, []);

  const handleRelaunchAI = useCallback(async () => {
    if (aiAnalyzing) return;
    setAiAnalyzing(true);
    try {
      await runUnderwritingAnalysis(applicationId, undefined, true, locale);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const app = await getApplication(applicationId);
          if (app.processing_status !== 'analyzing') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setAiAnalyzing(false);
            d.fetchClaimData();
          }
        } catch { /* ignore polling errors */ }
      }, 3000);
      setTimeout(() => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; setAiAnalyzing(false); } }, 120000);
    } catch (err) {
      setAiAnalyzing(false);
      const msg = err instanceof Error ? err.message : String(err);
      d.setError(msg || 'Échec de l\'analyse IA');
    }
  }, [applicationId, aiAnalyzing, d]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600" />
        <span className="ml-4 text-slate-600">{t('processingClaim')}</span>
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-slate-100">
      {/* ── Header strip ── */}
      <div className="bg-white border-b border-slate-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-red-100 rounded-lg"><Car className="h-5 w-5 text-red-600" /></div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900">{resolvedDisplayTitle || `${t('automotiveClaimTitle')}${applicationId}`}</h1>
              <p className="text-xs text-slate-500">{d.mediaItems.length} {t('evidenceFiles').toLowerCase()}</p>
            </div>
          </div>
          {/* Payout KPI strip */}
          <div className="flex items-center gap-6">
            <div className="text-right">
              <p className="text-[10px] text-emerald-600 font-medium uppercase tracking-wider">{t('recommendedPayout')}</p>
              <p className="text-2xl font-bold text-emerald-700">{(d.estimatedAmount || 0).toLocaleString('fr-FR')} €</p>
            </div>
            <div className="h-10 w-px bg-slate-200" />
            <div className="flex gap-4 text-center text-xs text-slate-500">
              <div><p className="text-lg font-bold text-slate-900">{d.mediaItems.length}</p>{t('evidenceFiles')}</div>
              <div><p className="text-lg font-bold text-slate-900">{d.assessment?.damage_areas?.length || 0}</p>{t('damageAreas')}</div>
              <div><p className={`text-lg font-bold ${(d.assessment?.fraud_indicators?.length || 0) > 0 ? 'text-amber-600' : 'text-slate-900'}`}>{d.assessment?.fraud_indicators?.length || 0}</p>{t('fraudFlags')}</div>
            </div>
            <div className="h-10 w-px bg-slate-200" />
            <label className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 cursor-pointer transition-colors">
              <Upload className="w-4 h-4" />{d.isUploading ? t('uploading') : t('uploadEvidence')}
              <input type="file" multiple accept="image/*,video/*,.pdf" onChange={d.handleFileUpload} className="hidden" disabled={d.isUploading} />
            </label>
            <button
              onClick={handleRelaunchAI}
              disabled={aiAnalyzing}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors disabled:opacity-50"
              title={t('reanalyzeAI')}
            >
              <RotateCcw className={`w-3.5 h-3.5 ${aiAnalyzing ? 'animate-spin' : ''}`} />
              {aiAnalyzing ? 'Analyse...' : 'Relancer IA'}
            </button>
            <button onClick={d.fetchClaimData} disabled={d.isRefreshing} title={t('refreshFile')} aria-label={t('refreshFile')} className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors disabled:opacity-50">
              <RefreshCw className={`w-4 h-4 ${d.isRefreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Decision bar — sticky below header (like Habitation) ── */}
      <UnderwritingDecisionFooter applicationId={applicationId} position="top" />

      {/* ── Fraud analysis — surfaced right below the decision banner (like Habitation) ── */}
      <div className="mx-4 mt-2">
        <FraudAnalysisPanel applicationId={applicationId} onFraudComplete={handleFraudComplete} />
      </div>

      {/* ── Communication Client — same banner placement as Fraud Analysis ── */}
      <div className="mx-4 mt-1">
        <CommunicationClientPanel
          applicationId={applicationId}
          insuredName={getExtractedText(d.application?.extracted_fields || {}, ['NomAssure', 'assure', 'Conducteur'])}
          claimReference={d.application?.external_reference || applicationId.slice(0, 8)}
          decisionStatus="pending"
          boardLabel="Sinistres Auto"
          severity={severityFromSentiment((d.application as any)?.sentiment_analysis)}
        />
      </div>

      {/* ── Customer 360 affiliation banner ── */}
      {d.application && !d.application.external_reference && (
        <CustomerAffiliationBanner
          applicationId={applicationId}
          suggestedName={getExtractedText(d.application?.extracted_fields || {}, ['NomAssure', 'assure', 'Conducteur'])}
          suggestedPhone={getExtractedText(d.application?.extracted_fields || {}, ['TelephoneAssure'])}
          suggestedEmail={getExtractedText(d.application?.extracted_fields || {}, ['EmailAssure'])}
          onAffiliated={() => d.fetchClaimData()}
        />
      )}

      {/* ── Error Banner ── */}
      {d.error && (
        <div className="mx-4 mt-2 bg-rose-50 border border-rose-200 rounded-lg px-4 py-2 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <p className="text-sm text-rose-700">{d.error}</p>
          <button onClick={() => d.setError(null)} title={t('closeError')} aria-label={t('closeError')} className="ml-auto text-rose-600 hover:text-rose-800"><XCircle className="w-4 h-4" /></button>
        </div>
      )}

      {/* ── Grid layout (like Habitation) ── */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-white border-t border-slate-200">
        {/* ROW 1: Synthèse IA + Analyse des risques + Pièces */}
        <div className="grid min-h-0 flex-[1_1_40%] grid-cols-12 divide-x divide-slate-200">
          {/* Synthèse IA — col 1-5 */}
          <div className="col-span-5 flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
              <Car className="w-4 h-4 text-red-600" />
              <span className="font-semibold text-slate-900 text-sm">{t('claimSummary')}</span>
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-indigo-50 text-indigo-600 border border-indigo-100"><Sparkles className="w-3 h-3" />{t('aiAnalysis')}</span>
              <span className={`ml-auto inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${d.severityInfo.bgColor} ${d.severityInfo.textColor} border ${d.severityInfo.borderColor}`}>
                {d.severityInfo.label || t('pendingAssessment')}
              </span>
            </div>
            <div className="flex-1 overflow-auto p-3 text-xs text-slate-700 space-y-3">
              {d.claimSummaryText ? (
                <p className="leading-relaxed">{d.claimSummaryText}</p>
              ) : d.assessment?.damage_areas && d.assessment.damage_areas.length > 0 ? (
                  <p className="leading-relaxed">
                    {t('claimDamageSummary', { zones: d.assessment.damage_areas.length, total: d.assessment.total_estimated_damage?.toLocaleString('fr-FR') || '0' })}
                    {d.assessment.liability?.fault_determination && <> {t('liabilityIndicates', { determination: d.assessment.liability.fault_determination, percentage: d.assessment.liability.fault_percentage || 0 })}</>}
                    {d.assessment.fraud_indicators && d.assessment.fraud_indicators.length > 0 && <> <span className="text-amber-600">⚠ {t('fraudIndicatorsDetected', { count: d.assessment.fraud_indicators.length })}</span></>}
                  </p>
                ) : (
                <p className="text-slate-500 italic">{t('processingEvidence')}</p>
              )}
              {/* Key Findings inline */}
              {(d.assessment?.damage_areas?.length || 0) > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">{t('keyFindings')}</div>
                  {d.assessment?.damage_areas?.slice(0, 4).map((area, idx) => (
                    <div key={idx} className="flex items-start gap-2 p-1.5 bg-slate-50 rounded-lg">
                      <span className={`px-1 py-0.5 text-[9px] font-medium rounded ${area.severity === 'severe' ? 'bg-rose-100 text-rose-700' : area.severity === 'moderate' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                        {SEVERITY_FR[area.severity?.toLowerCase() || ''] || area.severity?.toUpperCase()}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] font-medium text-slate-900">{trFr(LOCATION_FR, area.location?.replace(/_/g, ' ') || '')}</p>
                        <p className="text-[10px] text-slate-600 truncate">{trDesc(area.description || '')}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {/* Fraud indicators */}
              {(d.assessment?.fraud_indicators?.length || 0) > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[10px] font-medium text-amber-600 uppercase tracking-wider">{t('fraudAlerts')}</div>
                  {d.assessment?.fraud_indicators?.map((indicator, idx) => (
                    <div key={`fraud-${idx}`} className="flex items-start gap-2 p-1.5 bg-amber-50 rounded-lg border border-amber-200">
                      <AlertTriangle className="w-3 h-3 text-amber-600 mt-0.5 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] font-medium text-amber-800">{trFr(INDICATOR_TYPE_FR, indicator.indicator_type || '')}</p>
                        <p className="text-[10px] text-amber-700 truncate">{trDesc(indicator.description || '')}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Analyse des risques — col 6-8 */}
          <div className="col-span-3 flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
              <Shield className="w-4 h-4 text-red-600" />
              <span className="font-semibold text-slate-900 text-sm">{t('claimRiskAnalysis')}</span>
              <span className={`ml-auto text-xs font-medium ${d.severityInfo.textColor}`}>{d.severityInfo.label}</span>
            </div>
            <div className="flex-1 overflow-auto p-3 text-xs space-y-3">
              {d.assessment?.liability && (
                <p className="text-slate-700 leading-relaxed">
                  {d.assessment.liability.fault_determination === 'at_fault' ? t('claimantAtFault')
                    : d.assessment.liability.fault_determination === 'not_at_fault' ? t('claimantNotAtFault')
                    : t('liabilityShared')}
                  {d.assessment.fraud_indicators && d.assessment.fraud_indicators.length > 0
                    ? ` ${t('fraudRequiresReview', { count: d.assessment.fraud_indicators.length })}`
                    : ` ${t('noFraudDetected')}`}
                </p>
              )}
              <div className="pt-2 border-t border-slate-100">
                <div className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">{t('payoutRecommendation')}</div>
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-semibold ${(d.assessment?.fraud_indicators?.length || 0) > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
                    {(d.assessment?.fraud_indicators?.length || 0) > 0 ? t('reviewRequired') : t('approve')}
                  </span>
                </div>
                <p className="text-slate-600 mt-1">{t('recommendedLabel')} : <strong className="text-slate-900">{(d.estimatedAmount || 0).toLocaleString('fr-FR')} €</strong></p>
              </div>
            </div>
          </div>

          {/* Pièces justificatives — col 9-12 */}
          <div className="col-span-4 flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
              <FileText className="w-4 h-4 text-amber-600" />
              <span className="font-semibold text-slate-900 text-sm">Pièces ({d.mediaItems.length})</span>
            </div>
            <div className="flex-1 overflow-auto p-3 space-y-2">
              {/* Photos */}
              {d.images.length > 0 && (
                <div>
                  <div className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">{t('photos')} ({d.images.length})</div>
                  {d.images.slice(0, 4).map((img) => (
                    <div key={img.media_id} className="flex items-center gap-2 p-1 rounded hover:bg-slate-50 cursor-pointer" onClick={() => setSelectedImage(img)}>
                      <div className="w-8 h-8 rounded overflow-hidden bg-slate-100 flex-shrink-0"><img src={getMediaUrl(img.url)} alt={img.filename} className="w-full h-full object-cover" /></div>
                      <p className="text-[11px] text-slate-900 truncate flex-1">{img.filename}</p>
                      <Eye className="w-3 h-3 text-slate-400" />
                    </div>
                  ))}
                </div>
              )}
              {/* Documents */}
              {d.documents.length > 0 && (
                <div>
                  <div className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">{t('documents')} ({d.documents.length})</div>
                  {d.documents.map((doc) => (
                    <div key={doc.media_id} className="flex items-center gap-2 p-1 rounded hover:bg-slate-50 cursor-pointer" onClick={() => setSelectedPDF(doc)}>
                      <div className="w-6 h-8 rounded bg-rose-50 border border-rose-200 flex items-center justify-center flex-shrink-0"><FileText className="w-3 h-3 text-rose-500" /></div>
                      <p className="text-[11px] text-slate-900 truncate flex-1">{doc.filename}</p>
                      <Eye className="w-3 h-3 text-slate-400" />
                    </div>
                  ))}
                </div>
              )}
              {/* Vidéos */}
              {d.videos.length > 0 && (
                <div>
                  <div className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">{t('videos')} ({d.videos.length})</div>
                  {d.videos.map((vid) => (
                    <div key={vid.media_id} className="flex items-center gap-2 p-1 rounded hover:bg-slate-50 cursor-pointer" onClick={() => setShowVideoModal(true)}>
                      <div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center flex-shrink-0"><Play className="w-3 h-3 text-white" /></div>
                      <p className="text-[11px] text-slate-900 truncate flex-1">{vid.filename}</p>
                      <ChevronRight className="w-3 h-3 text-slate-400" />
                    </div>
                  ))}
                </div>
              )}
              {d.mediaItems.length === 0 && <p className="text-xs text-slate-500 italic text-center py-4">{t('noEvidenceItem')}</p>}
            </div>
          </div>
        </div>

        {/* ROW 2: Chronologie | Dommages */}
        <div className="grid min-h-0 flex-[1_1_30%] grid-cols-12 divide-x divide-slate-200 border-t border-slate-200">
          {/* Chronologie — col 1-6 */}
          <div className="col-span-6 flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
              <Clock className="w-4 h-4 text-indigo-600" />
              <span className="font-semibold text-slate-900 text-sm">{t('chronology')}</span>
            </div>
            <div className="flex-1 overflow-auto p-3">
              <div className="space-y-2">
                {d.timelineEvents.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <div className="w-10 text-slate-400 flex-shrink-0 font-mono text-[10px]">{e.date}</div>
                    <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${e.impact === 'supports' ? 'bg-emerald-500' : e.impact === 'disputes' ? 'bg-rose-500' : 'bg-slate-300'}`} />
                    <div className="min-w-0">
                      <div className="font-medium text-slate-900">{e.type}</div>
                      {e.desc && <div className="text-slate-500 truncate">{e.desc}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Dommages — col 7-12 */}
          <div className="col-span-6 flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-slate-50 flex-shrink-0">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              <span className="font-semibold text-slate-900 text-sm">{t('damagesObserved')}</span>
              <span className="ml-auto text-xs text-slate-500">{d.assessment?.damage_areas?.length || 0} zone(s)</span>
            </div>
            <div className="flex-1 overflow-auto p-3">
              {d.assessment?.damage_areas && d.assessment.damage_areas.length > 0 ? (
                <DamageViewer damageAreas={d.assessment.damage_areas} totalEstimate={d.assessment.total_estimated_damage || 0} />
              ) : (
                <p className="text-xs text-slate-500 italic text-center py-4">Aucun dommage identifié par l&apos;analyse</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Modals ── */}
      {selectedPDF && <PDFViewer url={selectedPDF.url} filename={selectedPDF.filename} onClose={() => setSelectedPDF(null)} />}

      {selectedImage && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={() => setSelectedImage(null)}>
          <button onClick={() => setSelectedImage(null)} title={t('closeImage')} aria-label={t('closeImage')} className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"><XCircle className="w-6 h-6 text-white" /></button>
          <img src={getMediaUrl(selectedImage.url)} alt={selectedImage.filename} className="max-w-[90vw] max-h-[90vh] object-contain" />
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/70 text-white px-4 py-2 rounded-lg">{selectedImage.filename}</div>
        </div>
      )}

      {showVideoModal && d.selectedVideo && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={() => setShowVideoModal(false)}>
          <button onClick={() => setShowVideoModal(false)} title={t('closeVideo')} aria-label={t('closeVideo')} className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"><XCircle className="w-6 h-6 text-white" /></button>
          <video src={getMediaUrl(d.selectedVideo.url)} controls autoPlay className="max-w-[90vw] max-h-[90vh]" onClick={(e) => e.stopPropagation()} />
        </div>
      )}

    </div>
  );
}

export default AutomotiveClaimsOverview;