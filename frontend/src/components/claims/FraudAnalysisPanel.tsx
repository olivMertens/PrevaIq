'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Shield, AlertTriangle, CheckCircle, XCircle, Loader2, Eye, FileWarning, Zap, Brain, Cpu, X, Info, CircleAlert, FileCheck, FileX, Globe, Copy, Check, ExternalLink, Maximize2 } from 'lucide-react';
import { FraudAnalysisResponse, runFraudAnalysis, getFraudAnalysis } from '@/lib/api';
import { useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';
import ConfidenceIndicator from '../ConfidenceIndicator';

type ReasoningEffort = 'low' | 'medium' | 'high';

// Full-screen detail dialog for a single section
function SectionDetailDialog({ title, open, onClose, children }: { title: string; open: boolean; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl 2xl:max-w-6xl max-h-[90vh] flex flex-col overflow-hidden mx-4" onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between flex-shrink-0">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-6">{children}</div>
      </div>
    </div>
  );
}

// Section header with expand button
function SectionHeader({ title, onExpand }: { title: string; onExpand: () => void }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">{title}</h3>
      <button onClick={onExpand} title="Agrandir" className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-slate-200 bg-white hover:bg-slate-50 text-slate-500 hover:text-slate-700 transition-colors text-[10px] font-medium shadow-sm">
        <Maximize2 className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">Détail</span>
      </button>
    </div>
  );
}

// Normalize a web intelligence finding to a consistent shape
function normalizeFinding(f: unknown): { title: string; summary: string; sourceUrl: string; supportsClaim?: boolean; relevance: string; examples?: string[] } {
  if (typeof f === 'string') return { title: '', summary: f, sourceUrl: '', relevance: '' };
  const obj = f as Record<string, unknown>;
  return {
    title: String(obj.title || obj.type || obj.category || ''),
    summary: String(obj.summary || obj.details || obj.description || ''),
    sourceUrl: String(obj.source_url || obj.source || ''),
    supportsClaim: obj.supports_claim as boolean | undefined,
    relevance: String(obj.relevance || ''),
    examples: Array.isArray(obj.examples) ? obj.examples.map(String) : undefined,
  };
}

interface FraudAnalysisPanelProps {
  applicationId: string;
  onFraudComplete?: (result: FraudAnalysisResponse) => void;
}

// Estimated duration in seconds per effort level (used for progress simulation)
const EFFORT_DURATION: Record<ReasoningEffort, number> = { low: 30, medium: 90, high: 240 };

const EFFORT_OPTIONS: { value: ReasoningEffort; icon: typeof Zap; label: string; desc: string; time: string }[] = [
  { value: 'low', icon: Zap, label: 'Rapide', desc: 'Vérification basique des images', time: '~30 sec' },
  { value: 'medium', icon: Cpu, label: 'Standard', desc: 'Analyse équilibrée — images + déclaration', time: '~1-2 min' },
  { value: 'high', icon: Brain, label: 'Approfondi', desc: 'Investigation complète — croisement multi-sources', time: '~3-5 min' },
];

export default function FraudAnalysisPanel({ applicationId, onFraudComplete }: FraudAnalysisPanelProps) {
  const t = useTranslations('fraudAnalysis');
  const [result, setResult] = useState<FraudAnalysisResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [effort, setEffort] = useState<ReasoningEffort>('medium');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const [copied, setCopied] = useState(false);
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  // Cleanup progress timer
  useEffect(() => {
    return () => { if (progressRef.current) clearInterval(progressRef.current); };
  }, []);

  // Load previously saved fraud analysis on mount (from application metadata)
  useEffect(() => {
    // Use the applications endpoint which already includes fraud_analysis
    // This avoids 404 errors on /api/claims/{id}/fraud-analysis for new dossiers
    import('@/lib/api').then(({ getApplication }) => {
      getApplication(applicationId).then((app) => {
        const fa = (app as unknown as Record<string, unknown>)?.fraud_analysis;
        if (fa && typeof fa === 'object') {
          const saved = fa as FraudAnalysisResponse;
          setResult(saved);
          onFraudComplete?.(saved);
        }
      }).catch(() => {
        // Fallback: try claims endpoint (multimodal pipeline)
        getFraudAnalysis(applicationId).then((saved) => {
          if (saved) { setResult(saved); onFraudComplete?.(saved); }
        }).catch(() => {});
      });
    });
  }, [applicationId, onFraudComplete]);

  const handleAnalyze = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setProgress(0);
    setDialogOpen(false); // Close dialog — run in background

    // Start progress simulation based on estimated duration
    startTimeRef.current = Date.now();
    const estimatedMs = EFFORT_DURATION[effort] * 1000;
    if (progressRef.current) clearInterval(progressRef.current);
    progressRef.current = setInterval(() => {
      const elapsed = Date.now() - startTimeRef.current;
      // Asymptotic curve: approaches 95% but never reaches 100%
      const pct = Math.min(95, Math.round((1 - Math.exp(-2.5 * elapsed / estimatedMs)) * 100));
      setProgress(pct);
    }, 500);

    try {
      const data = await runFraudAnalysis(applicationId, undefined, effort);
      setResult(data);
      onFraudComplete?.(data);
      setProgress(100);
      setDialogOpen(true); // Auto-open dialog with results
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fraud analysis failed');
      setProgress(0);
    } finally {
      setIsLoading(false);
      if (progressRef.current) { clearInterval(progressRef.current); progressRef.current = null; }
    }
  }, [applicationId, effort]);

  const generateMarkdown = useCallback((): string => {
    if (!result) return '';
    const lines: string[] = [];
    lines.push(`# Rapport d'analyse de fraude`);
    lines.push(`**Dossier** : ${result.application_id}`);
    lines.push(`**Date** : ${result.analysis_timestamp || new Date().toISOString()}`);
    lines.push('');

    // Overall assessment
    const oa = result.overall_assessment;
    if (oa) {
      lines.push(`## Évaluation globale`);
      lines.push(`- **Niveau de risque** : ${oa.overall_fraud_risk}`);
      lines.push(`- **Score de risque** : ${Math.round((oa.risk_score || 0) * 100)}%`);
      if (oa.siu_referral_recommended) {
        lines.push(`- **⚠ Renvoi SIU recommandé** : ${oa.siu_referral_reason || 'Oui'}`);
      }
      if (oa.summary) {
        lines.push('');
        lines.push(oa.summary);
      }
      lines.push('');

      // Attention items
      if (oa.attention_items && oa.attention_items.length > 0) {
        lines.push(`### Points d'attention`);
        for (const item of oa.attention_items) {
          lines.push(`- **${item.label}** (${item.priority}) : ${item.detail}`);
        }
        lines.push('');
      }

      // Dossier concordance
      if (oa.dossier_concordance) {
        lines.push(`### Concordance du dossier`);
        lines.push(`Score : ${Math.round((oa.dossier_concordance.score || 0) * 100)}%`);
        if (oa.dossier_concordance.field_checks) {
          lines.push('');
          lines.push('| Champ | Déclaré | Observé | Concordance |');
          lines.push('|-------|---------|---------|-------------|');
          for (const fc of oa.dossier_concordance.field_checks) {
            lines.push(`| ${fc.field} | ${fc.declared} | ${fc.observed} | ${fc.match ? '✅' : '❌'} |`);
          }
        }
        lines.push('');
      }

      // Fraud indicators
      if (oa.fraud_indicators && oa.fraud_indicators.length > 0) {
        lines.push(`### Indicateurs de fraude`);
        for (const ind of oa.fraud_indicators) {
          lines.push(`- **${ind.indicator_type}** (${ind.severity}) : ${ind.description}`);
        }
        lines.push('');
      }
    }

    // Image analyses
    if (result.image_analyses.length > 0) {
      lines.push(`## Analyse d'authenticité des images`);
      for (const img of result.image_analyses) {
        const status = img.error ? '⚠ Erreur' : img.is_likely_authentic ? '✅ Authentique' : '🔴 Suspect';
        lines.push(`### ${img.filename}`);
        lines.push(`**Statut** : ${status} | **Score** : ${Math.round((img.authenticity_score || 0) * 100)}%`);
        if (img.filename_concordance) {
          const fc = img.filename_concordance;
          if (!fc.filename_is_descriptive) {
            lines.push(`- Nom de fichier générique (non descriptif)`);
          } else if (fc.matches_content === false) {
            lines.push(`- ⚠ Nom de fichier ne correspond pas au contenu`);
            if (fc.expected_content && fc.actual_content) {
              lines.push(`  - Déclaré : ${fc.expected_content} — Observé : ${fc.actual_content}`);
            }
          } else if (fc.matches_content) {
            lines.push(`- ✅ Nom de fichier correspond au contenu`);
          }
        }
        if (img.manipulation_indicators && img.manipulation_indicators.length > 0) {
          for (const ind of img.manipulation_indicators) {
            lines.push(`- ${ind.description || ind.indicator}`);
          }
        }
        if (img.error) {
          lines.push(`- Erreur : ${img.error}`);
        }
        lines.push('');
      }
    }

    // Declaration verification
    const dv = result.declaration_verification;
    if (dv) {
      lines.push(`## Vérification déclaration vs preuves`);
      lines.push(`**Cohérence globale** : ${dv.overall_consistent ? '✅ Cohérent' : '❌ Incohérences détectées'} — ${Math.round((dv.consistency_score || 0) * 100)}%`);
      if (dv.discrepancies && dv.discrepancies.length > 0) {
        lines.push('');
        for (const d of dv.discrepancies) {
          lines.push(`- **${d.aspect}** : Déclaré: ${d.declared} | Observé: ${d.observed}`);
        }
      }
      lines.push('');
    }

    // Web Intelligence
    const wi = result.web_intelligence;
    if (wi && !wi.error) {
      lines.push(`## Renseignement Web (Bing WebSearch)`);
      if (wi.event_verified !== undefined && wi.event_verified !== null) {
        lines.push(`**Événement vérifié** : ${wi.event_verified ? '✅ Confirmé' : '❌ Non confirmé'}`);
      }
      if (wi.overall_assessment) {
        lines.push('');
        lines.push(wi.overall_assessment);
      }
      if (wi.findings && wi.findings.length > 0) {
        lines.push('');
        lines.push('### Résultats');
        for (const f of wi.findings) {
          if (typeof f === 'string') {
            lines.push(`- ℹ️ ${f}`);
          } else {
            const title = f.title || f.type || f.category || 'Info';
            const summary = f.summary || f.details || f.description || '';
            const source = f.source_url || f.source || '';
            const icon = f.supports_claim === true ? '✅' : f.supports_claim === false ? '❌' : 'ℹ️';
            lines.push(`- ${icon} **${title}** : ${summary}`);
            if (source) lines.push(`  - Source : ${source}`);
          }
        }
      }
      if (wi.source_urls && wi.source_urls.length > 0) {
        lines.push('');
        lines.push('### Sources');
        for (const url of wi.source_urls) {
          lines.push(`- ${url}`);
        }
      }
      lines.push('');
    }

    lines.push('---');
    lines.push(`*Rapport généré par ${brand.name} — ${new Date().toLocaleString('fr-FR')}*`);
    return lines.join('\n');
  }, [result]);

  const handleCopy = useCallback(async () => {
    const md = generateMarkdown();
    if (!md) return;
    try {
      await navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const ta = document.createElement('textarea');
      ta.value = md;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [generateMarkdown]);

  // Close on Escape
  useEffect(() => {
    if (!dialogOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setDialogOpen(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [dialogOpen]);

  // Close on backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
      setDialogOpen(false);
    }
  };

  const riskColors: Record<string, { bg: string; text: string; border: string }> = {
    LOW: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
    MODERATE: { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
    HIGH: { bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200' },
  };

  const riskLevel = result?.overall_assessment?.overall_fraud_risk || 'LOW';
  const colors = riskColors[riskLevel] || riskColors.LOW;

  return (
    <>
      {/* Compact inline trigger bar */}
      <div className="border-t border-slate-200 px-4 py-2.5 bg-slate-50">
        <div className="flex items-center gap-3">
          <Shield className="w-4 h-4 text-purple-600 flex-shrink-0" />
          <span className="text-sm font-medium text-slate-700">{t('title')}</span>
          {isLoading ? (
            <span className="ml-1 inline-flex items-center gap-1.5 text-xs text-purple-600">
              <Loader2 className="w-3 h-3 animate-spin" />
              {t('analyzing').split('—')[0].trim()} — {progress}%
            </span>
          ) : result ? (
            <span className={`ml-1 px-2 py-0.5 rounded-full text-xs font-semibold ${colors.bg} ${colors.text} border ${colors.border}`}>
              {t(`risk.${riskLevel}`)} — {Math.round((result.overall_assessment?.risk_score || 0) * 100)}%
            </span>
          ) : error ? (
            <span className="ml-1 text-xs text-rose-500">{error}</span>
          ) : (
            <span className="ml-1 text-xs text-slate-400">{t('notYetRun')}</span>
          )}
          <button
            onClick={() => setDialogOpen(true)}
            disabled={isLoading}
            className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-purple-700 bg-purple-50 border border-purple-200 rounded-lg hover:bg-purple-100 transition-colors disabled:opacity-50"
          >
            <Eye className="w-3.5 h-3.5" />
            {result ? t('viewResults') : t('runAnalysis')}
          </button>
        </div>
        {/* Progress bar — visible during background analysis */}
        {isLoading && (
          <div className="mt-2 h-1.5 bg-purple-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-purple-500 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>

      {/* Dialog overlay */}
      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={handleBackdropClick}>
          <div ref={dialogRef} className="bg-white rounded-xl shadow-2xl w-full max-w-2xl lg:max-w-4xl 2xl:max-w-5xl max-h-[85vh] flex flex-col overflow-hidden mx-4">
            {/* Dialog header */}
            <div className="px-6 py-4 bg-slate-50 border-b border-slate-100 flex items-center gap-3 flex-shrink-0">
              <div className="w-9 h-9 rounded-lg bg-purple-100 flex items-center justify-center text-purple-600">
                <Shield className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <h2 className="text-base font-semibold text-slate-900">{t('title')}</h2>
                <p className="text-xs text-slate-500">{t('description')}</p>
              </div>
              {result && (
                <div className={`px-3 py-1 rounded-full text-xs font-semibold ${colors.bg} ${colors.text} border ${colors.border}`}>
                  {t(`risk.${riskLevel}`)}
                </div>
              )}
              {result && (
                <button
                  onClick={handleCopy}
                  title={t('copyMarkdown')}
                  className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  {copied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                </button>
              )}
              <button onClick={() => setDialogOpen(false)} title="Fermer" className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Dialog body */}
            <div className="flex-1 overflow-auto p-6 space-y-5">
              {/* Results content */}
              {result && (
                <>
                  {/* Overall Risk */}
                  {result.overall_assessment && (
                    <div className={`p-4 rounded-lg ${colors.bg} border ${colors.border}`}>
                      <div className="flex items-center gap-2 mb-2">
                        {riskLevel === 'HIGH' && <AlertTriangle className={`w-5 h-5 ${colors.text}`} />}
                        {riskLevel === 'MODERATE' && <FileWarning className={`w-5 h-5 ${colors.text}`} />}
                        {riskLevel === 'LOW' && <CheckCircle className={`w-5 h-5 ${colors.text}`} />}
                        <span className={`text-sm font-semibold ${colors.text}`}>
                          {t('riskScore')}: {Math.round((result.overall_assessment.risk_score || 0) * 100)}%
                        </span>
                      </div>
                      {result.overall_assessment.summary && (
                        <p className={`text-sm ${colors.text} opacity-90`}>{result.overall_assessment.summary}</p>
                      )}
                      {result.overall_assessment.siu_referral_recommended && (
                        <div className="mt-2 flex items-center gap-2 text-sm font-medium text-rose-700">
                          <AlertTriangle className="w-4 h-4" />
                          {t('siuReferral')}
                          {result.overall_assessment.siu_referral_reason && (
                            <span className="font-normal text-xs text-rose-600 ml-1">— {result.overall_assessment.siu_referral_reason}</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Attention Items for Case Manager */}
                  {result.overall_assessment?.attention_items && result.overall_assessment.attention_items.length > 0 && (
                    <div>
                      <SectionHeader title={t('attentionItems')} onExpand={() => setExpandedSection('attention')} />
                      <div className="space-y-2">
                        {result.overall_assessment.attention_items.map((item, idx) => {
                          const priorityStyles: Record<string, { bg: string; border: string; icon: string; badge: string }> = {
                            high: { bg: 'bg-rose-50', border: 'border-rose-200', icon: 'text-rose-600', badge: 'bg-rose-100 text-rose-700' },
                            medium: { bg: 'bg-amber-50', border: 'border-amber-200', icon: 'text-amber-600', badge: 'bg-amber-100 text-amber-700' },
                            low: { bg: 'bg-sky-50', border: 'border-sky-200', icon: 'text-sky-600', badge: 'bg-sky-100 text-sky-700' },
                          };
                          const style = priorityStyles[item.priority] || priorityStyles.low;
                          const PriorityIcon = item.priority === 'high' ? CircleAlert : item.priority === 'medium' ? AlertTriangle : Info;
                          return (
                            <div key={idx} className={`flex items-start gap-3 p-3 rounded-lg border ${style.bg} ${style.border}`}>
                              <PriorityIcon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${style.icon}`} />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-0.5">
                                  <span className="text-sm font-medium text-slate-800">{String(item.label)}</span>
                                  <span className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded ${style.badge}`}>
                                    {t(`priority.${item.priority}`)}
                                  </span>
                                </div>
                                <p className="text-xs text-slate-600 leading-relaxed">{String(item.detail)}</p>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Dossier Concordance */}
                  {result.overall_assessment?.dossier_concordance && (
                    <div>
                      <SectionHeader title={t('dossierConcordance')} onExpand={() => setExpandedSection('concordance')} />
                      <div className={`p-4 rounded-lg border ${
                        result.overall_assessment.dossier_concordance.overall_match
                          ? 'bg-emerald-50 border-emerald-200'
                          : 'bg-amber-50 border-amber-200'
                      }`}>
                        <div className="flex items-center gap-2 mb-2">
                          {result.overall_assessment.dossier_concordance.overall_match ? (
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-amber-600" />
                          )}
                          <span className={`text-sm font-medium ${
                            result.overall_assessment.dossier_concordance.overall_match ? 'text-emerald-700' : 'text-amber-700'
                          }`}>
                            {t('concordanceScore')}: {Math.round((result.overall_assessment.dossier_concordance.score || 0) * 100)}%
                          </span>
                        </div>
                        {result.overall_assessment.dossier_concordance.field_checks?.map((fc, i) => (
                          <div key={i} className="mt-2 p-2 bg-white rounded text-xs border border-slate-100 flex items-start gap-2">
                            {fc.match ? (
                              <CheckCircle className="w-3 h-3 mt-0.5 text-emerald-500 flex-shrink-0" />
                            ) : (
                              <XCircle className="w-3 h-3 mt-0.5 text-rose-500 flex-shrink-0" />
                            )}
                            <div className="flex-1">
                              <div className="font-medium text-slate-800 capitalize">{fc.field}</div>
                              <div className="text-slate-600 mt-0.5">
                                <span className="text-slate-500">{t('declared')}: </span>{fc.declared}
                              </div>
                              <div className="text-slate-600">
                                <span className="text-slate-500">{t('observed')}: </span>{fc.observed}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Image Analyses */}
                  {result.image_analyses.length > 0 && (
                    <div>
                      <SectionHeader title={t('imageAnalysis')} onExpand={() => setExpandedSection('images')} />
                      <div className="space-y-3">
                        {result.image_analyses.map((img, idx) => (
                          <div key={idx} className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-sm font-medium text-slate-900">{img.filename}</span>
                              <div className="flex items-center gap-2">
                                {img.error ? (
                                <span className="text-xs text-rose-600">
                                  {img.error.includes('"') || img.error.includes('\\n') || img.error.startsWith('{')
                                    ? t('analysisError')
                                    : img.error}
                                </span>
                                ) : (
                                  <>
                                    {img.is_likely_authentic ? (
                                      <span className="inline-flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
                                        <CheckCircle className="w-3 h-3" />{t('authentic')}
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center gap-1 text-xs text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full">
                                        <XCircle className="w-3 h-3" />{t('suspicious')}
                                      </span>
                                    )}
                                    <ConfidenceIndicator confidence={img.authenticity_score || 0} />
                                  </>
                                )}
                              </div>
                            </div>
                            {/* Filename concordance indicator */}
                            {img.filename_concordance && (
                              <div className="mb-2">
                                {img.filename_concordance.filename_is_descriptive ? (
                                  img.filename_concordance.matches_content ? (
                                    <div className="flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 px-2 py-1 rounded">
                                      <FileCheck className="w-3 h-3 flex-shrink-0" />
                                      <span>{t('nameMatchesContent')}</span>
                                    </div>
                                  ) : img.filename_concordance.matches_content === false ? (
                                    <div className="flex items-start gap-1.5 text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded">
                                      <FileX className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                      <div>
                                        <span className="font-medium">{t('nameMismatch')}</span>
                                        {img.filename_concordance.expected_content && img.filename_concordance.actual_content && (
                                          <div className="mt-0.5 text-amber-600">
                                            {t('declared')}: {img.filename_concordance.expected_content} — {t('observed')}: {img.filename_concordance.actual_content}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  ) : null
                                ) : (
                                  <div className="flex items-center gap-1.5 text-xs text-slate-400 px-2 py-1">
                                    <Info className="w-3 h-3 flex-shrink-0" />
                                    <span>{t('genericFilename')}</span>
                                  </div>
                                )}
                              </div>
                            )}
                            {img.manipulation_indicators && img.manipulation_indicators.length > 0 && (
                              <div className="mt-2 space-y-1">
                                {img.manipulation_indicators.map((ind, i) => (
                                  <div key={i} className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 p-2 rounded">
                                    <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                    <span>{ind.description || ind.indicator}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Declaration Verification */}
                  {result.declaration_verification && (
                    <div>
                      <SectionHeader title={t('declarationCheck')} onExpand={() => setExpandedSection('declaration')} />
                      <div className={`p-4 rounded-lg border ${
                        result.declaration_verification.overall_consistent
                          ? 'bg-emerald-50 border-emerald-200'
                          : 'bg-amber-50 border-amber-200'
                      }`}>
                        <div className="flex items-center gap-2 mb-2">
                          {result.declaration_verification.overall_consistent ? (
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-amber-600" />
                          )}
                          <span className={`text-sm font-medium ${
                            result.declaration_verification.overall_consistent ? 'text-emerald-700' : 'text-amber-700'
                          }`}>
                            {result.declaration_verification.overall_consistent ? t('declarationConsistent') : t('declarationInconsistent')}
                          </span>
                          <span className="text-xs text-slate-500 ml-auto">
                            {Math.round((result.declaration_verification.consistency_score || 0) * 100)}%
                          </span>
                        </div>
                        {result.declaration_verification.discrepancies?.map((d, i) => (
                          <div key={i} className="mt-2 p-2 bg-white rounded text-xs border border-amber-100">
                            <div className="font-medium text-slate-800">{d.aspect}</div>
                            <div className="text-slate-600 mt-1">
                              <span className="text-rose-600">{t('declared')}: </span>{d.declared}
                            </div>
                            <div className="text-slate-600">
                              <span className="text-emerald-600">{t('observed')}: </span>{d.observed}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Web Intelligence — Bing WebSearch findings */}
                  {result.web_intelligence && !result.web_intelligence.error && (
                    <div>
                      <SectionHeader title={t('webIntelligence')} onExpand={() => setExpandedSection('webintel')} />
                      <div className={`p-4 rounded-lg border ${
                        result.web_intelligence.event_verified
                          ? 'bg-emerald-50 border-emerald-200'
                          : result.web_intelligence.event_verified === false
                          ? 'bg-rose-50 border-rose-200'
                          : 'bg-slate-50 border-slate-200'
                      }`}>
                        <div className="flex items-center gap-2 mb-2">
                          <Globe className="w-4 h-4 text-indigo-600" />
                          <span className="text-sm font-medium text-slate-800">
                            {result.web_intelligence.event_verified === true
                              ? t('eventVerified')
                              : result.web_intelligence.event_verified === false
                              ? t('eventNotVerified')
                              : t('eventUnknown')}
                          </span>
                          {result.web_intelligence.confidence != null && (
                            <span className="text-xs text-slate-500 ml-auto">
                              {typeof result.web_intelligence.confidence === 'number'
                                ? `${Math.round(result.web_intelligence.confidence * 100)}%`
                                : String(result.web_intelligence.confidence)}
                            </span>
                          )}
                        </div>
                        {result.web_intelligence.overall_assessment && !result.web_intelligence.overall_assessment.match(/sorry|cannot assist|can't assist|je ne peux pas/i) && (
                          <p className="text-xs text-slate-600 mb-2">{String(result.web_intelligence.overall_assessment)}</p>
                        )}
                        {result.web_intelligence.overall_assessment?.match(/sorry|cannot assist|can't assist|je ne peux pas/i) && (
                          <p className="text-xs text-amber-600 mb-2">Service de vérification web temporairement indisponible. Les résultats de recherche internet n&apos;ont pas pu être obtenus pour ce dossier.</p>
                        )}
                        {result.web_intelligence.findings?.map((f, i) => {
                          const { title, summary, sourceUrl, supportsClaim, relevance, examples } = normalizeFinding(f);
                          return (
                          <div key={i} className="mt-2 p-2 bg-white rounded text-xs border border-slate-100 flex items-start gap-2">
                            {supportsClaim === true ? (
                              <CheckCircle className="w-3 h-3 mt-0.5 text-emerald-500 flex-shrink-0" />
                            ) : supportsClaim === false ? (
                              <XCircle className="w-3 h-3 mt-0.5 text-rose-500 flex-shrink-0" />
                            ) : (
                              <Info className="w-3 h-3 mt-0.5 text-indigo-400 flex-shrink-0" />
                            )}
                            <div className="flex-1 min-w-0">
                              {title && <div className="font-medium text-slate-800">{title}</div>}
                              {summary && <div className="text-slate-600 mt-0.5">{summary}</div>}
                              {examples && examples.length > 0 && (
                                <ul className="mt-1 space-y-0.5 text-slate-500">
                                  {examples.map((ex, j) => (
                                    <li key={j} className="flex items-start gap-1">
                                      <span className="text-indigo-400 mt-0.5">•</span>
                                      <span>{ex}</span>
                                    </li>
                                  ))}
                                </ul>
                              )}
                              {sourceUrl && (() => { try { const u = new URL(sourceUrl); return (
                                <a href={sourceUrl} target="_blank" rel="noopener noreferrer"
                                   className="inline-flex items-center gap-1 mt-1 text-indigo-600 hover:text-indigo-800 hover:underline text-[11px]">
                                  <ExternalLink className="w-3 h-3 flex-shrink-0" />{u.hostname}{u.pathname.length > 1 ? u.pathname.slice(0, 40) : ''}
                                </a>
                              ); } catch { return (
                                <span className="inline-flex items-center gap-1 mt-1 text-slate-500 text-[10px]">
                                  <Info className="w-2.5 h-2.5" />{sourceUrl}
                                </span>
                              ); } })()}
                            </div>
                            {relevance && (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                relevance === 'high' ? 'bg-rose-100 text-rose-700'
                                : relevance === 'medium' ? 'bg-amber-100 text-amber-700'
                                : 'bg-slate-100 text-slate-600'
                              }`}>{relevance}</span>
                            )}
                          </div>
                          );
                        })}
                        {result.web_intelligence.source_urls && result.web_intelligence.source_urls.length > 0 && (
                          <div className="mt-3 pt-2 border-t border-slate-100">
                            <div className="text-[10px] text-slate-400 uppercase mb-1">{t('sources')}</div>
                            <div className="flex flex-wrap gap-1">
                              {result.web_intelligence.source_urls.map((url, i) => (
                                <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                                   className="inline-flex items-center gap-1 text-[11px] text-indigo-600 hover:underline bg-indigo-50 px-2 py-1 rounded border border-indigo-100 hover:bg-indigo-100 transition-colors">
                                  <ExternalLink className="w-3 h-3 flex-shrink-0" />
                                  {(() => { try { return new URL(url).hostname; } catch { return url.slice(0, 40); } })()}
                                </a>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Fraud Indicators */}
                  {result.overall_assessment && result.overall_assessment.fraud_indicators?.length > 0 && (
                    <div>
                      <SectionHeader title={t('indicators')} onExpand={() => setExpandedSection('indicators')} />
                      <div className="space-y-2">
                        {result.overall_assessment.fraud_indicators.map((ind, idx) => (
                          <div key={idx} className="flex items-start gap-3 p-3 bg-amber-50 rounded-lg border border-amber-200">
                            <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                            <div className="flex-1">
                              <p className="text-sm font-medium text-amber-800">{ind.indicator_type}</p>
                              <p className="text-xs text-amber-700">{ind.description}</p>
                            </div>
                            {ind.confidence && <ConfidenceIndicator confidence={ind.confidence} />}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Error */}
              {error && <p className="text-sm text-rose-600 text-center">{error}</p>}
            </div>

            {/* Dialog footer — effort selector + run button */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex flex-col gap-3 flex-shrink-0">
              <div className="flex items-center gap-3">
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{t('reasoningEffort')}</label>
                <div className="flex gap-1.5 flex-1">
                  {EFFORT_OPTIONS.map((opt) => {
                    const Icon = opt.icon;
                    const isActive = effort === opt.value;
                    return (
                      <button
                        key={opt.value}
                        onClick={() => setEffort(opt.value)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md border text-xs font-medium transition-all ${
                          isActive
                            ? 'border-purple-300 bg-purple-50 text-purple-700'
                            : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                        }`}
                        title={opt.desc}
                      >
                        <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-purple-600' : 'text-slate-400'}`} />
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">
                  {EFFORT_OPTIONS.find(o => o.value === effort)?.desc} — durée estimée : <span className="font-medium">{EFFORT_OPTIONS.find(o => o.value === effort)?.time}</span>
                </p>
              <button
                onClick={handleAnalyze}
                disabled={isLoading}
                className="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50"
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
                {result ? t('rerunAnalysis') : t('runAnalysis')}
              </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Expanded section dialogs */}
      {result && (
        <>
          {/* Attention Items — expanded */}
          <SectionDetailDialog title={t('attentionItems')} open={expandedSection === 'attention'} onClose={() => setExpandedSection(null)}>
            <div className="space-y-3">
              {result.overall_assessment?.attention_items?.map((item, idx) => {
                const priorityStyles: Record<string, { bg: string; border: string; icon: string; badge: string }> = {
                  high: { bg: 'bg-rose-50', border: 'border-rose-200', icon: 'text-rose-600', badge: 'bg-rose-100 text-rose-700' },
                  medium: { bg: 'bg-amber-50', border: 'border-amber-200', icon: 'text-amber-600', badge: 'bg-amber-100 text-amber-700' },
                  low: { bg: 'bg-sky-50', border: 'border-sky-200', icon: 'text-sky-600', badge: 'bg-sky-100 text-sky-700' },
                };
                const style = priorityStyles[item.priority] || priorityStyles.low;
                const PriorityIcon = item.priority === 'high' ? CircleAlert : item.priority === 'medium' ? AlertTriangle : Info;
                return (
                  <div key={idx} className={`flex items-start gap-4 p-4 rounded-lg border ${style.bg} ${style.border}`}>
                    <PriorityIcon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${style.icon}`} />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-base font-medium text-slate-800">{String(item.label)}</span>
                        <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded ${style.badge}`}>{t(`priority.${item.priority}`)}</span>
                      </div>
                      <p className="text-sm text-slate-600 leading-relaxed">{String(item.detail)}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </SectionDetailDialog>

          {/* Concordance — expanded */}
          <SectionDetailDialog title={t('dossierConcordance')} open={expandedSection === 'concordance'} onClose={() => setExpandedSection(null)}>
            {result.overall_assessment?.dossier_concordance && (
              <div>
                <div className="flex items-center gap-2 mb-4">
                  {result.overall_assessment.dossier_concordance.overall_match
                    ? <CheckCircle className="w-5 h-5 text-emerald-600" />
                    : <AlertTriangle className="w-5 h-5 text-amber-600" />}
                  <span className="text-lg font-medium">{t('concordanceScore')}: {Math.round((result.overall_assessment.dossier_concordance.score || 0) * 100)}%</span>
                </div>
                <table className="w-full text-sm border-collapse">
                  <thead><tr className="bg-slate-50"><th className="text-left p-3 border-b font-medium text-slate-700">Champ</th><th className="text-left p-3 border-b font-medium text-slate-700">{t('declared')}</th><th className="text-left p-3 border-b font-medium text-slate-700">{t('observed')}</th><th className="p-3 border-b w-10"></th></tr></thead>
                  <tbody>
                    {result.overall_assessment.dossier_concordance.field_checks?.map((fc, i) => (
                      <tr key={i} className="border-b border-slate-100">
                        <td className="p-3 font-medium text-slate-800 capitalize">{fc.field}</td>
                        <td className="p-3 text-slate-600">{fc.declared}</td>
                        <td className="p-3 text-slate-600">{fc.observed}</td>
                        <td className="p-3">{fc.match ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <XCircle className="w-4 h-4 text-rose-500" />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionDetailDialog>

          {/* Images — expanded */}
          <SectionDetailDialog title={t('imageAnalysis')} open={expandedSection === 'images'} onClose={() => setExpandedSection(null)}>
            <div className="space-y-4">
              {result.image_analyses.map((img, idx) => (
                <div key={idx} className="p-4 bg-slate-50 rounded-lg border border-slate-200">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-base font-medium text-slate-900">{img.filename}</span>
                    <div className="flex items-center gap-2">
                      {img.error ? <span className="text-sm text-rose-600">{t('analysisError')}</span> : img.is_likely_authentic
                        ? <span className="inline-flex items-center gap-1 text-sm text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200"><CheckCircle className="w-4 h-4" />{t('authentic')}</span>
                        : <span className="inline-flex items-center gap-1 text-sm text-rose-700 bg-rose-50 px-3 py-1 rounded-full border border-rose-200"><XCircle className="w-4 h-4" />{t('suspicious')}</span>}
                      {!img.error && <ConfidenceIndicator confidence={img.authenticity_score || 0} />}
                    </div>
                  </div>
                  {img.filename_concordance && !img.filename_concordance.filename_is_descriptive && (
                    <div className="flex items-center gap-2 text-sm text-slate-400 mb-2"><Info className="w-4 h-4" />{t('genericFilename')}</div>
                  )}
                  {img.filename_concordance?.filename_is_descriptive && img.filename_concordance.matches_content === false && (
                    <div className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 p-3 rounded mb-2 border border-amber-200">
                      <FileX className="w-4 h-4 mt-0.5 flex-shrink-0" />
                      <div><span className="font-medium">{t('nameMismatch')}</span>
                        {img.filename_concordance.expected_content && <div className="mt-1 text-amber-600">{t('declared')}: {img.filename_concordance.expected_content} — {t('observed')}: {img.filename_concordance.actual_content}</div>}
                      </div>
                    </div>
                  )}
                  {img.manipulation_indicators && img.manipulation_indicators.length > 0 && (
                    <div className="space-y-2">
                      {img.manipulation_indicators.map((ind, i) => (
                        <div key={i} className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 p-3 rounded border border-amber-200">
                          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                          <span>{ind.description || ind.indicator}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </SectionDetailDialog>

          {/* Declaration — expanded */}
          <SectionDetailDialog title={t('declarationCheck')} open={expandedSection === 'declaration'} onClose={() => setExpandedSection(null)}>
            {result.declaration_verification && (
              <div>
                <div className="flex items-center gap-3 mb-4">
                  {result.declaration_verification.overall_consistent
                    ? <CheckCircle className="w-5 h-5 text-emerald-600" />
                    : <AlertTriangle className="w-5 h-5 text-amber-600" />}
                  <span className="text-lg font-medium">
                    {result.declaration_verification.overall_consistent ? t('declarationConsistent') : t('declarationInconsistent')}
                  </span>
                  <span className="text-sm text-slate-500">{Math.round((result.declaration_verification.consistency_score || 0) * 100)}%</span>
                </div>
                <div className="space-y-3">
                  {result.declaration_verification.discrepancies?.map((d, i) => (
                    <div key={i} className="p-4 bg-white rounded-lg border border-amber-200">
                      <div className="text-base font-medium text-slate-800 mb-2">{d.aspect}</div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div><span className="text-rose-600 font-medium">{t('declared')}</span><p className="text-slate-600 mt-1">{d.declared}</p></div>
                        <div><span className="text-emerald-600 font-medium">{t('observed')}</span><p className="text-slate-600 mt-1">{d.observed}</p></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </SectionDetailDialog>

          {/* Web Intelligence — expanded */}
          <SectionDetailDialog title={t('webIntelligence')} open={expandedSection === 'webintel'} onClose={() => setExpandedSection(null)}>
            {result.web_intelligence && (
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <Globe className="w-5 h-5 text-indigo-600" />
                  <span className="text-lg font-medium text-slate-800">
                    {result.web_intelligence.event_verified === true ? t('eventVerified')
                      : result.web_intelligence.event_verified === false ? t('eventNotVerified')
                      : t('eventUnknown')}
                  </span>
                  {result.web_intelligence.confidence != null && (
                    <span className="text-sm text-slate-500">
                      {typeof result.web_intelligence.confidence === 'number'
                        ? `${Math.round(result.web_intelligence.confidence * 100)}%`
                        : String(result.web_intelligence.confidence)}
                    </span>
                  )}
                </div>
                {result.web_intelligence.overall_assessment && (
                  <p className="text-sm text-slate-600 mb-4 leading-relaxed">{result.web_intelligence.overall_assessment}</p>
                )}
                <div className="space-y-3">
                  {result.web_intelligence.findings?.map((f, i) => {
                    const { title, summary, sourceUrl, supportsClaim, relevance, examples } = normalizeFinding(f);
                    return (
                      <div key={i} className="p-4 bg-white rounded-lg border border-slate-200 flex items-start gap-3">
                        {supportsClaim === true ? <CheckCircle className="w-5 h-5 mt-0.5 text-emerald-500 flex-shrink-0" />
                          : supportsClaim === false ? <XCircle className="w-5 h-5 mt-0.5 text-rose-500 flex-shrink-0" />
                          : <Info className="w-5 h-5 mt-0.5 text-indigo-400 flex-shrink-0" />}
                        <div className="flex-1 min-w-0">
                          {title && <div className="text-base font-medium text-slate-800">{title}</div>}
                          {summary && <div className="text-sm text-slate-600 mt-1 leading-relaxed">{summary}</div>}
                          {examples && examples.length > 0 && (
                            <ul className="mt-2 space-y-1 text-sm text-slate-500">
                              {examples.map((ex, j) => (
                                <li key={j} className="flex items-start gap-2"><span className="text-indigo-400 mt-0.5">•</span><span>{ex}</span></li>
                              ))}
                            </ul>
                          )}
                          {sourceUrl && (() => { try { const u = new URL(sourceUrl); return (
                            <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 mt-2 text-indigo-600 hover:text-indigo-800 hover:underline text-sm">
                              <ExternalLink className="w-4 h-4 flex-shrink-0" />{u.hostname}{u.pathname.length > 1 ? u.pathname.slice(0, 60) : ''}
                            </a>
                          ); } catch { return <span className="text-sm text-slate-500 mt-2">{sourceUrl}</span>; } })()}
                        </div>
                        {relevance && <span className={`text-xs px-2 py-1 rounded font-medium ${relevance === 'high' ? 'bg-rose-100 text-rose-700' : relevance === 'medium' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>{relevance}</span>}
                      </div>
                    );
                  })}
                </div>
                {result.web_intelligence.source_urls && result.web_intelligence.source_urls.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-slate-200">
                    <div className="text-xs text-slate-400 uppercase mb-2">{t('sources')}</div>
                    <div className="flex flex-wrap gap-2">
                      {result.web_intelligence.source_urls.map((url, i) => (
                        <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:underline bg-indigo-50 px-3 py-1.5 rounded-lg border border-indigo-100 hover:bg-indigo-100 transition-colors">
                          <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
                          {(() => { try { return new URL(url).hostname; } catch { return url.slice(0, 40); } })()}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </SectionDetailDialog>

          {/* Indicators — expanded */}
          <SectionDetailDialog title={t('indicators')} open={expandedSection === 'indicators'} onClose={() => setExpandedSection(null)}>
            <div className="space-y-3">
              {result.overall_assessment?.fraud_indicators?.map((ind, idx) => (
                <div key={idx} className="flex items-start gap-4 p-4 bg-amber-50 rounded-lg border border-amber-200">
                  <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <p className="text-base font-medium text-amber-800">{ind.indicator_type}</p>
                    <p className="text-sm text-amber-700 mt-1 leading-relaxed">{ind.description}</p>
                  </div>
                  {ind.confidence && <ConfidenceIndicator confidence={ind.confidence} />}
                </div>
              ))}
            </div>
          </SectionDetailDialog>
        </>
      )}
    </>
  );
}
