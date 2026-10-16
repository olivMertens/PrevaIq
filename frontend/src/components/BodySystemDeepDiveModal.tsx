'use client';

import React, { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { X, Download, Sparkles, RefreshCw, Loader2, Users } from 'lucide-react';
import { useTranslations, useLocale } from 'next-intl';
import { brand } from '@/lib/brand';
import BodyDiagram from './BodyDiagram';
import PendingInvestigationsCard from './PendingInvestigationsCard';
import LastOfficeVisitCard from './LastOfficeVisitCard';
import BodySystemCard from './BodySystemCard';
import AbnormalLabsCard from './AbnormalLabsCard';
import LatestVitalsCard from './LatestVitalsCard';
import FloatingPdfPreview from './FloatingPdfPreview';
import { PageRefBadges } from './PageRefBadge';
import type { ApplicationMetadata, DeepDiveData, ParsedOutput } from '@/lib/types';
import { getDeepDiveData, runDeepDiveAnalysis, pollForDeepDiveCompletion } from '@/lib/api';
import { useToast } from '@/lib/ToastProvider';

interface BodySystemDeepDiveModalProps {
  isOpen: boolean;
  onClose: () => void;
  application: ApplicationMetadata;
  onNavigateToPage?: (page: number) => void;
  onRerunAnalysis?: () => Promise<void>;
  onApplicationUpdate?: (app: ApplicationMetadata) => void;
}

export default function BodySystemDeepDiveModal({
  isOpen,
  onClose,
  application,
  onNavigateToPage,
  onRerunAnalysis,
  onApplicationUpdate,
}: BodySystemDeepDiveModalProps) {
  const { addToast } = useToast();
  const t = useTranslations('deepDive');
  const tReport = useTranslations('deepDive.report');
  const locale = useLocale();
  const modalRef = useRef<HTMLDivElement>(null);
  const detailPanelRef = useRef<HTMLDivElement>(null);
  const systemRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [isRerunning, setIsRerunning] = useState(false);
  const [rerunStatus, setRerunStatus] = useState<string>('');
  const [currentApp, setCurrentApp] = useState<ApplicationMetadata>(application);
  // Floating PDF preview state
  const [pdfPreview, setPdfPreview] = useState<{ page: number; rect: DOMRect } | null>(null);
  const hoverTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  // Update current app when prop changes
  useEffect(() => {
    setCurrentApp(application);
  }, [application]);
  
  // Cleanup timeout on unmount or close
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      if (hoverTimerRef.current) {
        clearTimeout(hoverTimerRef.current);
        hoverTimerRef.current = null;
      }
    };
  }, []);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [isOpen]);

  const handlePageClick = useCallback(
    (page: number) => {
      onNavigateToPage?.(page);
    },
    [onNavigateToPage]
  );

  const handleRegionClick = useCallback((systemCode: string) => {
    const el = systemRefs.current.get(systemCode);
    if (el && detailPanelRef.current) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  // Floating PDF preview handlers — show after a short hover delay
  const handlePageHover = useCallback((page: number, rect: DOMRect) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => {
      setPdfPreview({ page, rect });
    }, 350); // 350ms delay to avoid flicker on quick mouse-throughs
  }, []);

  const handlePageLeave = useCallback(() => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    // Don't close immediately — let the FloatingPdfPreview's own onMouseLeave handle it
  }, []);

  const closePdfPreview = useCallback(() => {
    setPdfPreview(null);
  }, []);

  // Determine PDF file name for the floating preview
  const pdfFileName = useMemo(() => {
    const files = currentApp.files || [];
    const pdf = files.find(f => f.filename.toLowerCase().endsWith('.pdf'));
    return pdf?.filename || '';
  }, [currentApp.files]);

  /** Build a complete HTML report of the deep dive and open it in a print-ready window. */
  const handleExportFullReport = useCallback(() => {
    const dd: DeepDiveData = getDeepDiveData(currentApp);
    const caseRef = currentApp.external_reference || currentApp.id;
    const intlLocale = locale === 'en' ? 'en-US' : 'fr-FR';
    const now = new Date().toLocaleString(intlLocale);
    const htmlLang = locale === 'en' ? 'en' : 'fr';

    // ---------- helpers ----------
    const esc = (s: string | undefined | null) =>
      (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    const pageRefs = (pages?: number[]) =>
      pages && pages.length ? ` <span style="color:#6366f1;font-size:11px">[p.${pages.join(', p.')}]</span>` : '';

    // ---------- sections ----------
    const sections: string[] = [];

    // Pending Investigations
    const pi = dd.pendingInvestigations;
    if (pi?.pending_investigations?.length) {
      let html = `<h2>${tReport('pendingInvestigations')}</h2>`;
      if (pi.summary) html += `<p>${esc(pi.summary)}</p>`;
      html += '<ul>';
      for (const inv of pi.pending_investigations) {
        html += `<li><strong>${esc(inv.urgency?.toUpperCase())}</strong> (${esc(inv.type)}) — ${esc(inv.description)}${pageRefs(inv.page_references)}</li>`;
      }
      html += '</ul>';
      sections.push(html);
    }

    // Last Office Visit
    const lov = dd.lastOfficeVisit;
    if (lov?.last_office_visit) {
      let html = `<h2>${tReport('lastOfficeVisit')}</h2>`;
      html += `<p><strong>${tReport('dateLabel')}</strong> ${esc(lov.last_office_visit.date)}${pageRefs(lov.last_office_visit.page_references)}</p>`;
      html += `<p>${esc(lov.last_office_visit.summary)}</p>`;
      if (lov.last_office_visit.follow_up_plans?.length) {
        html += `<p><strong>${tReport('followUpPlans')}</strong></p><ul>`;
        for (const plan of lov.last_office_visit.follow_up_plans) {
          html += `<li>${esc(plan)}</li>`;
        }
        html += '</ul>';
      }
      if (lov.last_labs) {
        html += `<h3>${tReport('lastLabs')}</h3>`;
        html += `<p><strong>${tReport('dateLabel')}</strong> ${esc(lov.last_labs.date)}${pageRefs(lov.last_labs.page_references)}</p>`;
        html += `<p>${esc(lov.last_labs.summary)}</p>`;
      }
      sections.push(html);
    }

    // Body System Review
    const bsr = dd.bodySystemReview;
    if (bsr?.body_systems?.length) {
      let html = `<h2>${tReport('bodySystemReview')}</h2>`;
      for (const sys of bsr.body_systems) {
        html += `<h3>${esc(sys.system_name)} (${esc(sys.system_code)}) — <span style="text-transform:capitalize">${esc(sys.severity)}</span></h3>`;
        for (const dx of sys.diagnoses) {
          html += `<h4>${esc(dx.name)} — <em>${esc(dx.status)}</em>${dx.date_diagnosed ? ` (${tReport('diagnosedAt', { date: esc(dx.date_diagnosed) })})` : ''}${pageRefs(dx.page_references)}</h4>`;
          if (dx.treatments?.length) {
            html += `<p><strong>${tReport('treatments')}</strong></p><ul>`;
            for (const tx of dx.treatments) {
              html += `<li>${esc(tx.date)} — ${esc(tx.description)}${pageRefs(tx.page_references)}</li>`;
            }
            html += '</ul>';
          }
          if (dx.consults?.length) {
            html += `<p><strong>${tReport('consults')}</strong></p><ul>`;
            for (const c of dx.consults) {
              html += `<li>${esc(c.date)} — ${esc(c.specialist)}: ${esc(c.summary)}${pageRefs(c.page_references)}</li>`;
            }
            html += '</ul>';
          }
          if (dx.imaging?.length) {
            html += `<p><strong>${tReport('imaging')}</strong></p><ul>`;
            for (const img of dx.imaging) {
              html += `<li>${esc(img.date)} — ${esc(img.type)}: ${esc(img.result)}${pageRefs(img.page_references)}</li>`;
            }
            html += '</ul>';
          }
        }
      }
      sections.push(html);
    }

    // Abnormal Labs
    const al = dd.abnormalLabs;
    if (al?.abnormal_labs?.length) {
      let html = `<h2>${tReport('abnormalLabs')}</h2>`;
      html += '<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:12px"><thead><tr>';
      html += `<th>${tReport('tableDate')}</th><th>${tReport('tableTest')}</th><th>${tReport('tableValue')}</th><th>${tReport('tableRefRange')}</th><th>${tReport('tableInterpretation')}</th><th>${tReport('tableSource')}</th></tr></thead><tbody>`;
      for (const lab of al.abnormal_labs) {
        html += `<tr><td>${esc(lab.date)}</td><td>${esc(lab.test_name)}</td><td>${esc(lab.value)} ${esc(lab.unit)}</td><td>${esc(lab.reference_range)}</td><td>${esc(lab.interpretation)}</td><td>${pageRefs(lab.page_references)}</td></tr>`;
      }
      html += '</tbody></table>';
      sections.push(html);
    }

    // Latest Vitals
    const vt = dd.latestVitals;
    if (vt?.latest_vitals) {
      const v = vt.latest_vitals;
      let html = `<h2>${tReport('latestVitals')}</h2>`;
      if (v.date) html += `<p><strong>${tReport('dateLabel')}</strong> ${esc(v.date)}${pageRefs(v.page_references)}</p>`;
      const items: string[] = [];
      if (v.blood_pressure) items.push(`${tReport('vitalsBp')}: ${v.blood_pressure.systolic}/${v.blood_pressure.diastolic} mmHg`);
      if (v.heart_rate != null) items.push(`${tReport('vitalsHr')}: ${v.heart_rate} bpm`);
      if (v.weight) items.push(`${tReport('vitalsWeight')}: ${v.weight.value} ${v.weight.unit || 'lbs'}`);
      if (v.height) items.push(`${tReport('vitalsHeight')}: ${v.height.value}`);
      if (v.bmi != null) items.push(`${tReport('vitalsBmi')}: ${v.bmi}`);
      if (v.temperature != null) items.push(`${tReport('vitalsTemp')}: ${v.temperature} °F`);
      if (v.respiratory_rate != null) items.push(`${tReport('vitalsRr')}: ${v.respiratory_rate}/min`);
      if (v.oxygen_saturation != null) items.push(`${tReport('vitalsSpo2')}: ${v.oxygen_saturation}%`);
      html += `<p>${items.join(' &nbsp;|&nbsp; ')}</p>`;
      sections.push(html);
    }

    // Family History
    const fam = dd.familyHistory as (ParsedOutput & { relatives?: Array<{ relationship: string; condition: string; age_at_onset?: string; age_at_death?: string; notes?: string; page_references?: number[] }> }) | null;
    if (fam?.relatives?.length) {
      let html = `<h2>${tReport('familyHistoryTitle')}</h2>`;
      if (fam.summary) html += `<p>${esc(fam.summary)}</p>`;
      html += '<ul>';
      for (const rel of fam.relatives) {
        let line = `<strong>${esc(rel.relationship)}</strong> — ${esc(rel.condition)}`;
        if (rel.age_at_onset) line += ` (${tReport('ageAt', { age: esc(rel.age_at_onset) })})`;
        if (rel.age_at_death) line += tReport('deceasedAt', { age: esc(rel.age_at_death) });
        if (rel.notes) line += ` — ${esc(rel.notes)}`;
        html += `<li>${line}${pageRefs(rel.page_references)}</li>`;
      }
      html += '</ul>';
      sections.push(html);
    }

    // Assemble full document
    const fullHtml = `<!DOCTYPE html>
<html lang="${htmlLang}"><head><meta charset="utf-8"><title>${tReport('windowTitle', { ref: esc(caseRef) })}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1e293b; font-size: 13px; line-height: 1.6; }
  h1 { font-size: 20px; border-bottom: 2px solid #6366f1; padding-bottom: 6px; }
  h2 { font-size: 16px; color: #334155; margin-top: 1.5em; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
  h3 { font-size: 14px; color: #475569; }
  h4 { font-size: 13px; color: #64748b; }
  table { margin: 8px 0; }
  th { background: #f1f5f9; text-align: left; }
  ul { padding-left: 1.5em; }
  li { margin-bottom: 4px; }
  .meta { color: #94a3b8; font-size: 11px; }
  @media print { body { margin: 0; } }
</style></head><body>
<h1>${tReport('h1', { ref: esc(caseRef) })}</h1>
<p class="meta">${tReport('metaGenerated', { date: esc(now), brand: brand.name })}</p>
${sections.join('\n')}
</body></html>`;

    const win = window.open('', '_blank');
    if (win) {
      win.document.write(fullHtml);
      win.document.close();
      // Auto-trigger print dialog after a brief delay for rendering
      setTimeout(() => win.print(), 400);
    }
  }, [currentApp, tReport, locale]);
  
  const handleDeepDiveRerun = async (force: boolean = false) => {
    if (isRerunning) return;
    
    // Clear any existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    
    setIsRerunning(true);
    setRerunStatus(force ? t('forceRerunning') : t('startingAnalysis'));
    
    try {
      // Start deep dive in background
      await runDeepDiveAnalysis(currentApp.id, true, force);
      setRerunStatus(t('analysisRunning'));
      
      // Poll for completion (checks for processing_status !== 'analyzing')
      const updatedApp = await pollForDeepDiveCompletion(currentApp.id);
      setRerunStatus(t('analysisComplete'));
      setCurrentApp(updatedApp);
      onApplicationUpdate?.(updatedApp);
      setIsRerunning(false);
      
      timeoutRef.current = setTimeout(() => {
        setRerunStatus('');
        timeoutRef.current = null;
      }, 2000);
    } catch (err) {
      console.error('Failed to run deep dive:', err);
      const msg = err instanceof Error ? err.message : String(err);
      // Show specific error for missing document content
      if (msg.includes('document content') || msg.includes('extraction')) {
        addToast('error', tReport('extractionRequiredToast'));
        setRerunStatus(tReport('extractionRequiredStatus'));
      } else {
        addToast('error', msg || t('analysisFailed'));
        setRerunStatus(t('analysisFailedRetry'));
      }
      setIsRerunning(false);
      timeoutRef.current = setTimeout(() => {
        setRerunStatus('');
        timeoutRef.current = null;
      }, 5000);
    }
  };

  if (!isOpen) return null;

  const deepDive: DeepDiveData = getDeepDiveData(currentApp);
  const hasAnalysis = currentApp.status === 'completed' || !!currentApp.llm_outputs;
  const caseRef = currentApp.external_reference || currentApp.id;

  // Family history from existing analysis
  const familyHistory = deepDive.familyHistory as (ParsedOutput & { relatives?: Array<{ relationship: string; condition: string; age_at_onset?: string; age_at_death?: string; notes?: string; page_references?: number[] }> }) | null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div
        ref={modalRef}
        className="relative w-[95vw] h-[92vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-white flex-shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-slate-900">
              {t('title')}
            </h2>
            <span className="text-sm text-slate-500">— {caseRef}</span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-600 border border-indigo-100">
              <Sparkles className="w-3 h-3" />
              {t('aiAnalysis')}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleDeepDiveRerun(true)}
              disabled={isRerunning}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={t('forceRerunTitle')}
            >
              {isRerunning ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              {isRerunning ? t('analyzing') : t('rerun')}
            </button>
            <button
              onClick={handleExportFullReport}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
            >
              <Download className="w-4 h-4" />
              {t('export')}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        {!hasAnalysis ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <p className="text-slate-500 mb-4">{t('noAnalysis')}</p>
              <p className="text-sm text-slate-400">{t('runAnalysisToGenerate')}</p>
            </div>
          </div>
        ) : !deepDive.hasData ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-md">
              <p className="text-slate-500 mb-4">
                {t('analyzedBeforeDeepDive')}
              </p>
              {rerunStatus && (
                <div className="mb-4 p-3 bg-indigo-50 text-indigo-700 rounded-lg text-sm flex items-center gap-2 justify-center">
                  {isRerunning && <Loader2 className="w-4 h-4 animate-spin" />}
                  {rerunStatus}
                </div>
              )}
              <button
                onClick={() => handleDeepDiveRerun(false)}
                disabled={isRerunning}
                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isRerunning ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
                {isRerunning ? t('analyzing') : t('runDeepDiveAnalysis')}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Rerun status banner */}
            {rerunStatus && (
              <div className="px-6 py-2 bg-indigo-50 text-indigo-700 text-sm flex items-center gap-2 border-b border-indigo-100 flex-shrink-0">
                {isRerunning && <Loader2 className="w-4 h-4 animate-spin" />}
                {rerunStatus}
              </div>
            )}
            <div className="flex-1 flex overflow-hidden">
            {/* Left Panel — Body Diagram */}
            <div className="w-72 flex-shrink-0 border-r border-slate-200 overflow-y-auto p-4 bg-slate-50/50">
              <BodyDiagram
                bodySystems={deepDive.bodySystemReview?.body_systems || []}
                onRegionClick={handleRegionClick}
              />

              {/* Quick stats */}
              <div className="mt-4 space-y-2">
                <div className="bg-white rounded-lg p-3 border border-slate-200">
                  <div className="text-xs text-slate-500 mb-1">{t('pendingInvestigations')}</div>
                  <div className="text-lg font-semibold text-slate-800">
                    {deepDive.pendingInvestigations?.pending_investigations?.length || 0}
                  </div>
                </div>
                <div className="bg-white rounded-lg p-3 border border-slate-200">
                  <div className="text-xs text-slate-500 mb-1">{t('abnormalLabs')}</div>
                  <div className="text-lg font-semibold text-slate-800">
                    {deepDive.abnormalLabs?.abnormal_labs?.length || 0}
                  </div>
                </div>
              </div>
            </div>

            {/* Right Panel — Detail sections */}
            <div ref={detailPanelRef} className="flex-1 overflow-y-auto p-6 space-y-5">
              {/* Pending Investigations */}
              <PendingInvestigationsCard
                investigations={deepDive.pendingInvestigations?.pending_investigations || []}
                summary={deepDive.pendingInvestigations?.summary}
                onPageClick={handlePageClick}
                onPageHover={handlePageHover}
                onPageLeave={handlePageLeave}
              />

              {/* Last Office Visit & Labs */}
              <LastOfficeVisitCard
                lov={deepDive.lastOfficeVisit?.last_office_visit || null}
                lastLabs={deepDive.lastOfficeVisit?.last_labs || null}
                onPageClick={handlePageClick}
                onPageHover={handlePageHover}
                onPageLeave={handlePageLeave}
              />

              {/* Body System Cards */}
              {deepDive.bodySystemReview?.body_systems?.map((sys) => (
                <div
                  key={sys.system_code}
                  ref={(el) => {
                    if (el) systemRefs.current.set(sys.system_code, el);
                  }}
                >
                  <BodySystemCard system={sys} onPageClick={handlePageClick} onPageHover={handlePageHover} onPageLeave={handlePageLeave} />
                </div>
              ))}

              {/* Abnormal Labs */}
              <AbnormalLabsCard
                labs={deepDive.abnormalLabs?.abnormal_labs || []}
                onPageClick={handlePageClick}
                onPageHover={handlePageHover}
                onPageLeave={handlePageLeave}
              />

              {/* Latest Vitals */}
              <LatestVitalsCard
                vitals={deepDive.latestVitals?.latest_vitals || null}
                onPageClick={handlePageClick}
                onPageHover={handlePageHover}
                onPageLeave={handlePageLeave}
              />

              {/* Family History */}
              {familyHistory && (
                <div className="bg-white rounded-lg border border-slate-200 p-4">
                  <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2 mb-3">
                    <Users className="w-4 h-4 text-purple-500" /> {t('familyHistory')}
                  </h3>
                  {familyHistory.summary && (
                    <p className="text-sm text-slate-700 mb-3">{familyHistory.summary}</p>
                  )}
                  {familyHistory.relatives && familyHistory.relatives.length > 0 ? (
                    <ul className="space-y-1.5">
                      {familyHistory.relatives.map((rel, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                          <span className="text-slate-400">•</span>
                          <span>
                            <span className="font-medium">{rel.relationship}</span>
                            {' — '}
                            {rel.condition}
                            {rel.age_at_onset && ` (age ${rel.age_at_onset})`}
                            {rel.age_at_death && `, deceased (age ${rel.age_at_death})`}
                            {rel.notes && <span className="text-slate-500"> — {rel.notes}</span>}
                          </span>
                          {rel.page_references && (
                            <PageRefBadges pages={rel.page_references} onClick={handlePageClick} onHover={handlePageHover} onLeave={handlePageLeave} />
                          )}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-slate-500 italic">{t('noFamilyHistory')}</p>
                  )}
                </div>
              )}

              {/* Footer */}
              <div className="text-center py-4">
                <span className="text-xs text-slate-400">{t('poweredByAI')}</span>
              </div>
            </div>
          </div>
          </div>
        )}
      </div>

      {/* Floating PDF preview on page badge hover */}
      {pdfPreview && pdfFileName && (
        <FloatingPdfPreview
          applicationId={currentApp.id}
          fileName={pdfFileName}
          pageNumber={pdfPreview.page}
          anchorRect={pdfPreview.rect}
          onClose={closePdfPreview}
        />
      )}
    </div>
  );
}
