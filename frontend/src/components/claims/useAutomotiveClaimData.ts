'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  ClaimAssessmentResponse,
  MediaItem,
  Keyframe,
  AdjusterDecisionRequest,
  getClaimAssessment,
  getClaimMedia,
  getVideoKeyframes,
  updateAdjusterDecision,
  uploadClaimFiles,
  searchClaimsPolicies,
  ClaimsPolicySearchResult,
  getApplication,
} from '@/lib/api';
import type { ApplicationMetadata } from '@/lib/types';
import { useToast } from '@/lib/ToastProvider';
import { isWorkbenchSystem } from '@/lib/brand';

export default function useAutomotiveClaimData(applicationId: string) {
  const { addToast } = useToast();
  const t = useTranslations('claims');
  const [assessment, setAssessment] = useState<ClaimAssessmentResponse | null>(null);
  const [application, setApplication] = useState<ApplicationMetadata | null>(null);
  const [mediaItems, setMediaItems] = useState<MediaItem[]>([]);
  const [keyframes, setKeyframes] = useState<Keyframe[]>([]);
  const [videoDuration, setVideoDuration] = useState(0);
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
  const [policyResults, setPolicyResults] = useState<ClaimsPolicySearchResult[]>([]);
  const [policyQuery, setPolicyQuery] = useState('');
  const [isSearchingPolicies, setIsSearchingPolicies] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [decisionNotes, setDecisionNotes] = useState('');
  const [adjustedAmount, setAdjustedAmount] = useState<number | undefined>();
  const [error, setError] = useState<string | null>(null);

  const fetchClaimData = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    try {
      const [assessmentData, mediaData, appData] = await Promise.all([
        getClaimAssessment(applicationId).catch(() => null),
        getClaimMedia(applicationId),
        getApplication(applicationId),
      ]);
      if (assessmentData) setAssessment(assessmentData);
      setApplication(appData);
      setMediaItems(mediaData.media_items);

      const firstVideo = mediaData.media_items.find((m) => m.media_type === 'video');
      if (firstVideo) {
        setSelectedVideoId(firstVideo.media_id);
        const keyframeData = await getVideoKeyframes(applicationId, firstVideo.media_id);
        setKeyframes(keyframeData.keyframes);
        setVideoDuration(keyframeData.duration);
      }
    } catch (err) {
      console.error('Failed to fetch claim data:', err);
      setError(err instanceof Error ? err.message : 'Échec du chargement des données');
    } finally {
      setIsRefreshing(false);
    }
  }, [applicationId]);

  useEffect(() => {
    fetchClaimData();
  }, [fetchClaimData]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    setIsUploading(true);
    setError(null);
    try {
      await uploadClaimFiles(applicationId, Array.from(files));
      addToast('success', 'Fichiers téléversés avec succès');
      // Poll until backend processing completes (avoids flicker from stale data)
      const poll = setInterval(async () => {
        try {
          const res = await fetch(`/api/applications/${applicationId}`);
          if (res.ok) {
            const app = await res.json();
            if (!app.processing_status || app.processing_status === 'error') {
              clearInterval(poll);
              await fetchClaimData();
              setIsUploading(false);
            }
          }
        } catch { /* ignore polling errors */ }
      }, 3000);
      // Failsafe timeout
      setTimeout(() => { clearInterval(poll); setIsUploading(false); }, 120000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Échec du téléversement');
      addToast('error', 'Échec du téléversement des fichiers');
      setIsUploading(false);
    }
  };

  const handlePolicySearch = async () => {
    if (!policyQuery.trim()) return;
    setIsSearchingPolicies(true);
    try {
      const results = await searchClaimsPolicies({ query: policyQuery, limit: 10 });
      setPolicyResults(results.results);
    } catch (err) {
      console.error('Failed to search policies:', err);
    } finally {
      setIsSearchingPolicies(false);
    }
  };

  const handleDecision = async (
    decision: 'approve' | 'adjust' | 'deny' | 'investigate',
    callbacks?: { onApprove?: () => void; onAdjust?: () => void; onDeny?: () => void; onInvestigate?: () => void }
  ) => {
    try {
      const request: AdjusterDecisionRequest = {
        decision,
        notes: decisionNotes || undefined,
        adjusted_amount: decision === 'adjust' ? adjustedAmount : undefined,
      };
      await updateAdjusterDecision(applicationId, request);
      await fetchClaimData();
      addToast('success', `Décision "${decision}" enregistrée`);
      switch (decision) {
        case 'approve': callbacks?.onApprove?.(); break;
        case 'adjust': callbacks?.onAdjust?.(); break;
        case 'deny': callbacks?.onDeny?.(); break;
        case 'investigate': callbacks?.onInvestigate?.(); break;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Échec de l\'enregistrement');
      addToast('error', 'Erreur lors de l\'enregistrement de la décision');
    }
  };

  const images = mediaItems.filter((m) => m.media_type === 'image');
  const videos = mediaItems.filter((m) => m.media_type === 'video');
  const documents = mediaItems.filter((m) => m.media_type === 'document');
  const selectedVideo = mediaItems.find((m) => m.media_id === selectedVideoId);

  // Compute estimated amount from LLM outputs (claims engine returns 0 as default)
  const estimatedAmount = (() => {
    // Priority 1: claims engine payout_recommendation
    const payoutAmt = assessment?.payout_recommendation?.recommended_amount;
    if (payoutAmt && payoutAmt > 0) return payoutAmt;
    // Priority 2: LLM damage estimate from application metadata
    const llm = (application as unknown as Record<string, unknown>)?.llm_outputs as Record<string, Record<string, { parsed?: Record<string, unknown> }>> | undefined;
    if (llm) {
      for (const section of Object.values(llm)) {
        if (!section || typeof section !== 'object') continue;
        for (const sub of Object.values(section)) {
          const parsed = sub?.parsed;
          if (!parsed) continue;
          for (const key of ['total_damage_estimate', 'montant_indemnisation_recommande', 'recommended_amount', 'net_claim', 'claim_amount']) {
            const v = parsed[key];
            if (typeof v === 'number' && v > 0) return v;
          }
        }
      }
    }
    // Priority 3: extracted fields
    const ef = application?.extracted_fields || {};
    for (const [k, val] of Object.entries(ef)) {
      if (k.toLowerCase().includes('montant')) {
        const raw = String(typeof val === 'object' && val !== null && 'value' in val ? (val as { value: unknown }).value : val);
        const cleaned = raw.replace(/[€\s]/g, '').replace(',', '.');
        const num = parseFloat(cleaned);
        if (!isNaN(num) && num > 0) return num;
      }
    }
    return 0;
  })();

  // Build timeline events from application metadata
  const timelineEvents = (() => {
    if (!application) return [];
    const ef = application.extracted_fields || {};
    const getField = (names: string[]) => {
      for (const name of names) {
        const entry = ef[name] || Object.entries(ef).find(([k]) => k.endsWith(`:${name}`))?.[1];
        if (entry) return String(typeof entry === 'object' && entry !== null && 'value' in entry ? (entry as { value: unknown }).value : entry);
      }
      return '';
    };
    const fmtDate = (d: Date) => `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth() + 1).toString().padStart(2, '0')}`;
    const dateSinistre = getField(['DateSinistre', 'date_sinistre']);
    const nature = getField(['NatureSinistre', 'CauseOfLoss']);
    const vehicule = getField(['vehicule', 'MarqueVehicule']);
    const montant = getField(['MontantEstime', 'montant_facture', 'montant_devis', 'MontantTotal']);
    const dateDecl = getField(['DateDeclaration']);
    const dateClot = getField(['DateCloture']);

    let incidentDate: Date | null = null;
    if (dateSinistre) {
      const parts = dateSinistre.match(/(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})/);
      if (parts) incidentDate = new Date(Number(parts[3].length === 2 ? '20' + parts[3] : parts[3]), Number(parts[2]) - 1, Number(parts[1]));
    }
    const createdDate = application.created_at ? new Date(application.created_at) : new Date();
    const events: { date: string; type: string; desc: string; impact: string; sort: number }[] = [];

    if (incidentDate) {
      events.push({ date: fmtDate(incidentDate), type: t('timeline.incident', { nature: nature || 'Accident' }), desc: vehicule || '', impact: 'disputes', sort: incidentDate.getTime() });
    }

    if (dateDecl) {
      const parts = dateDecl.match(/(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})/);
      if (parts) {
        const d = new Date(Number(parts[3].length === 2 ? '20' + parts[3] : parts[3]), Number(parts[2]) - 1, Number(parts[1]));
        events.push({ date: fmtDate(d), type: t('timeline.declaration'), desc: t('timeline.declarationDescNoContract'), impact: 'supports', sort: d.getTime() });
      }
    } else if (incidentDate) {
      const d = new Date(incidentDate.getTime() + 2 * 86400000);
      events.push({ date: fmtDate(d), type: t('timeline.declaration'), desc: t('timeline.declarationDescNoContract'), impact: 'supports', sort: d.getTime() });
    }

    if (montant) {
      const formatted = !isNaN(Number(montant.replace(/[€\s,]/g, '').replace(',', '.'))) ? montant : montant;
      events.push({ date: fmtDate(createdDate), type: t('timeline.estimation', { amount: formatted }), desc: t('timeline.estimationDesc'), impact: 'neutral', sort: createdDate.getTime() });
    }

    events.push({ date: fmtDate(createdDate), type: t('timeline.reception'), desc: t('timeline.receptionDesc'), impact: 'supports', sort: createdDate.getTime() + 1 });

    if (application.status === 'completed' || application.llm_outputs) {
      events.push({ date: fmtDate(new Date()), type: t('timeline.analysisComplete'), desc: t('timeline.analysisCompleteDesc', { count: (application.files || []).length }), impact: 'supports', sort: Date.now() });
    }

    if (dateClot) {
      const parts = dateClot.match(/(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})/);
      if (parts) {
        const d = new Date(Number(parts[3].length === 2 ? '20' + parts[3] : parts[3]), Number(parts[2]) - 1, Number(parts[1]));
        events.push({ date: fmtDate(d), type: t('timeline.closure'), desc: t('timeline.closureDesc'), impact: 'supports', sort: d.getTime() });
      }
    }

    // Merge action_history (same pattern as habitation PropertyCasualtyClaimsOverview)
    if ((application as unknown as Record<string, unknown>)?.action_history) {
      const actionHistory = (application as unknown as Record<string, unknown>).action_history as Array<{
        at: string; label: string; performed?: string; systems?: string[];
      }>;
      for (const action of actionHistory) {
        const actionDate = new Date(action.at);
        const systems = (action.systems || []).filter((s: string) => s && !isWorkbenchSystem(s));
        const badges = systems.map((s: string) => {
          if (s === 'SIU') return '🔍 SIU';
          if (s === 'GED') return '📂 GED';
          if (s === 'Email') return '✉️ Email';
          return s;
        }).join(' · ');
        events.push({
          date: fmtDate(actionDate),
          type: action.label,
          desc: badges || action.performed || 'Action',
          impact: action.performed === 'HITL' ? 'disputes' : 'supports',
          sort: actionDate.getTime(),
        });
      }
    }

    events.sort((a, b) => a.sort - b.sort);
    return events.length > 0 ? events : [{ date: '—', type: t('timeline.waiting'), desc: '', impact: 'neutral', sort: 0 }];
  })();

  const claimSummaryText = (() => {
    const llm = (application as unknown as Record<string, unknown>)?.llm_outputs as
      | Record<string, Record<string, { parsed?: Record<string, unknown>; raw?: string }>>
      | undefined;
    if (llm) {
      for (const section of Object.values(llm)) {
        if (!section || typeof section !== 'object') continue;
        for (const sub of Object.values(section)) {
          const parsed = sub?.parsed;
          if (parsed && typeof parsed.summary === 'string' && parsed.summary.trim()) {
            return parsed.summary.trim();
          }
          if (parsed && typeof parsed.description === 'string' && parsed.description.trim()) {
            return parsed.description.trim();
          }
          if (sub?.raw && typeof sub.raw === 'string' && sub.raw.trim() && !sub.raw.includes('```')) {
            return sub.raw.trim().slice(0, 500);
          }
        }
      }
    }

    const ef = application?.extracted_fields || {};
    const getField = (names: string[]) => {
      for (const name of names) {
        const entry = ef[name] || Object.entries(ef).find(([k]) => k.endsWith(`:${name}`))?.[1];
        if (entry) return String(typeof entry === 'object' && entry !== null && 'value' in entry ? (entry as { value: unknown }).value : entry);
      }
      return '';
    };
    const description = getField(['IncidentDescription', 'DescriptionSinistre', 'NatureSinistre', 'CauseOfLoss']);
    const vehicle = getField(['vehicule', 'VehicleMake', 'MarqueVehicule', 'VehicleModel', 'ModeleVehicule']);
    const date = getField(['DateSinistre', 'date_sinistre']);
    if (description || vehicle || date) {
      return [
        description || 'Sinistre automobile déclaré',
        vehicle ? `Véhicule : ${vehicle}` : '',
        date ? `Date du sinistre : ${date}` : '',
      ].filter(Boolean).join('. ');
    }

    const evidence = mediaItems.find((item) => /dommage|crash|accident|choc|enfonc|fissur|rayur|porti[eè]re|pare.?chocs|aile|capot/i.test(item.filename));
    if (evidence) {
      const label = evidence.filename
        .replace(/\.[^.]+$/, '')
        .replace(/^(crash|accident|sinistre|photo|image)[_-]/i, '')
        .replace(/[_-]+/g, ' ')
        .trim();
      return `Sinistre automobile avec dommage visible sur la pièce justificative ${label || evidence.filename}.`;
    }

    return '';
  })();

  const getRiskLevel = (severity: string | undefined) => {
    const s = (severity || '').toLowerCase();
    if (s.includes('high') || s.includes('severe') || s.includes('heavy'))
      return { label: 'Élevé', bgColor: 'bg-rose-50', textColor: 'text-rose-700', borderColor: 'border-rose-200' };
    if (s.includes('moderate') || s.includes('medium'))
      return { label: 'Modéré', bgColor: 'bg-amber-50', textColor: 'text-amber-700', borderColor: 'border-amber-200' };
    return { label: 'Faible', bgColor: 'bg-emerald-50', textColor: 'text-emerald-700', borderColor: 'border-emerald-200' };
  };

  return {
    assessment, application, mediaItems, keyframes, videoDuration, selectedVideoId, selectedVideo,
    policyResults, policyQuery, isSearchingPolicies, isRefreshing, isUploading,
    decisionNotes, adjustedAmount, error,
    images, videos, documents, estimatedAmount, timelineEvents, claimSummaryText,
    severityInfo: getRiskLevel(assessment?.overall_severity),
    setPolicyQuery, setDecisionNotes, setAdjustedAmount, setError,
    fetchClaimData, handleFileUpload, handlePolicySearch, handleDecision,
    setPolicyResults,
  };
}
