'use client';

import React, { useMemo } from 'react';
import { Heart, Phone, Clock, MessageCircle, TrendingUp, UserCheck, Handshake, ChevronRight } from 'lucide-react';
import { useTranslations } from 'next-intl';
import clsx from 'clsx';

interface BackendSentiment {
  score: number;
  level: 'calm' | 'moderate' | 'stressed' | 'critical';
  suggestedTone?: 'empathetic' | 'standard' | 'formal';
  contextSummary?: string;
  factors?: string[];
  suggestions?: string[];
  agent?: string;
  computed_at?: string;
}

interface ClientSentimentPanelProps {
  /** Customer 360 profile data */
  customerData: Record<string, unknown> | null;
  /** Claim nature for sensitivity scoring */
  claimNature: string;
  /** Estimated amount */
  estimatedAmount: number;
  /** Number of days since claim was filed */
  daysSinceClaim: number;
  /** Backend sentiment from the Sentiment Agent (preferred when available) */
  backendSentiment?: BackendSentiment | null;
  /** Display mode: 'compact' shows top 2 factors+suggestions with "view more" link; 'full' shows everything. Default: 'compact'. */
  mode?: 'compact' | 'full';
  /** Called when user clicks "view more" link in compact mode (typically opens full modal) */
  onExpand?: () => void;
}

type SentimentLevel = 'calm' | 'concerned' | 'stressed' | 'critical';

interface SentimentResult {
  level: SentimentLevel;
  score: number; // 0-100
  emoji: string;
  label: string;
  color: string;
  bgColor: string;
  borderColor: string;
  factors: { label: string; impact: 'positive' | 'neutral' | 'negative'; detail: string }[];
  suggestions: { icon: typeof Phone; label: string; priority: 'high' | 'medium' | 'low' }[];
  isAI: boolean;
}

function levelToVisual(level: string, score: number) {
  if (level === 'critical' || score >= 70)
    return { emoji: '😟', label: 'Attention requise', color: 'text-rose-700', bgColor: 'bg-rose-50', borderColor: 'border-rose-200' };
  if (level === 'stressed' || score >= 50)
    return { emoji: '😐', label: 'Vigilance', color: 'text-amber-700', bgColor: 'bg-amber-50', borderColor: 'border-amber-200' };
  if (level === 'moderate' || level === 'concerned' || score >= 30)
    return { emoji: '🙂', label: 'Normal', color: 'text-slate-600', bgColor: 'bg-slate-50', borderColor: 'border-slate-200' };
  return { emoji: '😊', label: 'Serein', color: 'text-emerald-700', bgColor: 'bg-emerald-50', borderColor: 'border-emerald-200' };
}

export default function ClientSentimentPanel({
  customerData,
  claimNature,
  estimatedAmount,
  daysSinceClaim,
  backendSentiment,
  mode = 'compact',
  onExpand,
}: ClientSentimentPanelProps) {
  const t = useTranslations('claimsModals');
  const tSentiment = useTranslations('clientSentiment');
  const sentiment = useMemo<SentimentResult>(() => {
    // ── Prefer backend Sentiment Agent result ──
    if (backendSentiment && typeof backendSentiment.score === 'number') {
      const visual = levelToVisual(backendSentiment.level, backendSentiment.score);
      const factors: SentimentResult['factors'] = (backendSentiment.factors || []).map(f => {
        const isNeg = /frustrat|stress|élevé|critique|négatif|urgent|prolongé|traumat|insécur/i.test(f);
        const isPos = /satisf|fidèle|confiance|modéré|acceptable|rapide|positif|serein/i.test(f);
        return { label: '', impact: isNeg ? 'negative' as const : isPos ? 'positive' as const : 'neutral' as const, detail: f };
      });
      const iconMap: Record<string, typeof Phone> = { téléphone: Phone, empathi: Heart, accélér: Clock, proactif: MessageCircle, étapes: UserCheck, standard: TrendingUp };
      const suggestions: SentimentResult['suggestions'] = (backendSentiment.suggestions || []).map(s => {
        let icon: typeof Phone = MessageCircle;
        let priority: 'high' | 'medium' | 'low' = 'medium';
        for (const [keyword, ic] of Object.entries(iconMap)) { if (s.toLowerCase().includes(keyword)) { icon = ic; break; } }
        if (backendSentiment.score >= 70) priority = 'high';
        else if (backendSentiment.score < 30) priority = 'low';
        return { icon, label: s, priority };
      });
      return { ...visual, level: (backendSentiment.level === 'moderate' ? 'concerned' : backendSentiment.level) as SentimentLevel, score: backendSentiment.score, factors, suggestions, isAI: true };
    }

    // ── Fallback: local heuristic computation ──
    let score = 30; // Baseline neutral
    const factors: SentimentResult['factors'] = [];
    const suggestions: SentimentResult['suggestions'] = [];

    // Factor 1: Claim value impact on stress
    if (estimatedAmount > 10000) {
      score += 25;
      factors.push({ label: 'Montant élevé', impact: 'negative', detail: `${estimatedAmount.toLocaleString('fr-FR')} € — impact financier important` });
    } else if (estimatedAmount > 5000) {
      score += 15;
      factors.push({ label: 'Montant significatif', impact: 'negative', detail: `${estimatedAmount.toLocaleString('fr-FR')} € — préoccupation probable` });
    } else {
      factors.push({ label: 'Montant modéré', impact: 'positive', detail: `${estimatedAmount.toLocaleString('fr-FR')} € — impact limité` });
    }

    // Factor 2: Claim nature sensitivity
    const nature = claimNature.toLowerCase();
    if (nature.includes('incendie') || nature.includes('catastrophe')) {
      score += 20;
      factors.push({ label: 'Sinistre sensible', impact: 'negative', detail: 'Incendie ou catastrophe naturelle — traumatisme possible' });
    } else if (nature.includes('cambriolage') || nature.includes('vol')) {
      score += 15;
      factors.push({ label: 'Atteinte aux biens', impact: 'negative', detail: 'Vol ou cambriolage — sentiment d\'insécurité' });
    } else if (nature.includes('tempête') || nature.includes('inondation')) {
      score += 10;
      factors.push({ label: 'Événement climatique', impact: 'neutral', detail: 'Dommages liés à un phénomène naturel' });
    } else {
      factors.push({ label: 'Sinistre courant', impact: 'positive', detail: 'Dégât des eaux ou dommage standard' });
    }

    // Factor 3: Time elapsed
    if (daysSinceClaim > 30) {
      score += 20;
      factors.push({ label: 'Délai prolongé', impact: 'negative', detail: `${daysSinceClaim} jours depuis la déclaration — frustration probable` });
    } else if (daysSinceClaim > 14) {
      score += 10;
      factors.push({ label: 'Délai modéré', impact: 'neutral', detail: `${daysSinceClaim} jours — dans la norme mais attente ressentie` });
    } else {
      factors.push({ label: 'Traitement rapide', impact: 'positive', detail: `${daysSinceClaim} jours — délai acceptable` });
    }

    // Factor 4: Customer history (from C360)
    const profile = customerData?.profile as Record<string, unknown> | undefined;
    const claimHistory = customerData?.claim_history as Array<unknown> | undefined;
    const loyaltyYears = profile?.loyalty_years as number | undefined;

    if (claimHistory && claimHistory.length > 3) {
      score += 10;
      factors.push({ label: 'Multi-sinistré', impact: 'negative', detail: `${claimHistory.length} sinistres au dossier — client potentiellement lassé` });
    }

    if (loyaltyYears && loyaltyYears > 10) {
      score -= 5;
      factors.push({ label: 'Client fidèle', impact: 'positive', detail: `${loyaltyYears} ans de fidélité — relation de confiance` });
    }

    // Clamp score
    score = Math.max(0, Math.min(100, score));

    // Build suggestions based on score
    if (score >= 70) {
      suggestions.push({ icon: Phone, label: 'Contact téléphonique prioritaire recommandé', priority: 'high' });
      suggestions.push({ icon: Heart, label: 'Adopter un ton empathique et rassurant', priority: 'high' });
      suggestions.push({ icon: Clock, label: 'Accélérer le traitement si possible', priority: 'medium' });
    } else if (score >= 45) {
      suggestions.push({ icon: MessageCircle, label: 'Email personnalisé avec suivi proactif', priority: 'medium' });
      suggestions.push({ icon: UserCheck, label: 'Confirmer les prochaines étapes au client', priority: 'medium' });
    } else {
      suggestions.push({ icon: TrendingUp, label: 'Traitement standard — client satisfait', priority: 'low' });
    }

    const visual = levelToVisual('', score);
    let level: SentimentLevel;
    if (score >= 70) level = 'critical';
    else if (score >= 50) level = 'stressed';
    else if (score >= 30) level = 'concerned';
    else level = 'calm';

    return { ...visual, level, score, factors, suggestions, isAI: false };
  }, [customerData, claimNature, estimatedAmount, daysSinceClaim, backendSentiment]);

  // ── Compact mode: prioritize 'high' suggestions, then take top 2 of each ──
  const isCompact = mode === 'compact';
  const priorityOrder = { high: 0, medium: 1, low: 2 } as const;
  const sortedSuggestions = isCompact
    ? [...sentiment.suggestions].sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority])
    : sentiment.suggestions;
  const visibleFactors = isCompact ? sentiment.factors.slice(0, 2) : sentiment.factors;
  const visibleSuggestions = isCompact ? sortedSuggestions.slice(0, 2) : sortedSuggestions;
  const hiddenCount =
    (sentiment.factors.length - visibleFactors.length) +
    (sentiment.suggestions.length - visibleSuggestions.length);

  return (
    <div className={clsx('rounded-lg border p-3', sentiment.bgColor, sentiment.borderColor)}>
      {/* Header with score */}
      <div className="flex items-center gap-2 mb-2">
        <Handshake className={clsx('w-4 h-4', sentiment.color)} />
        <span className={clsx('text-xs font-semibold', sentiment.color)}>{tSentiment('title')}</span>
        <span className="text-lg ml-0.5">{sentiment.emoji}</span>
        <span className={clsx('text-[11px] font-medium', sentiment.color)}>{sentiment.label}</span>
        <div className="ml-auto flex items-center gap-1.5">
          {sentiment.isAI && <span className="text-[9px] px-1 py-0.5 rounded bg-indigo-50 text-indigo-600 border border-indigo-100 font-medium">IA</span>}
          <div className="w-16 h-1.5 bg-white/60 rounded-full overflow-hidden">
            <div
              className={clsx(
                'h-full rounded-full transition-all',
                sentiment.score >= 70 ? 'bg-rose-500' :
                sentiment.score >= 50 ? 'bg-amber-500' :
                sentiment.score >= 30 ? 'bg-slate-400' :
                'bg-emerald-500'
              )}
              style={{ width: `${sentiment.score}%` }}
            />
          </div>
          <span className={clsx('text-[10px] font-bold', sentiment.color)}>{sentiment.score}</span>
        </div>
      </div>

      {/* Factors */}
      <div className="space-y-1 mb-2">
        {visibleFactors.map((f, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[11px]">
            <span className={clsx(
              'w-1.5 h-1.5 rounded-full flex-shrink-0',
              f.impact === 'positive' ? 'bg-emerald-500' :
              f.impact === 'negative' ? 'bg-rose-500' :
              'bg-slate-400'
            )} />
            <span className="text-slate-600">{f.detail}</span>
          </div>
        ))}
      </div>

      {/* Suggestions */}
      {visibleSuggestions.length > 0 && (
        <div className="border-t border-white/40 pt-2 space-y-1">
          {visibleSuggestions.map((s, i) => {
            const Icon = s.icon;
            return (
              <div key={i} className="flex items-center gap-1.5 text-[11px]">
                <Icon className={clsx(
                  'w-3 h-3 flex-shrink-0',
                  s.priority === 'high' ? 'text-rose-500' :
                  s.priority === 'medium' ? 'text-amber-500' :
                  'text-slate-400'
                )} />
                <span className={clsx(
                  s.priority === 'high' ? 'font-medium text-rose-800' :
                  s.priority === 'medium' ? 'text-amber-800' :
                  'text-slate-500'
                )}>{s.label}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* "View more" link (compact mode only) */}
      {isCompact && hiddenCount > 0 && onExpand && (
        <button
          type="button"
          onClick={onExpand}
          className={clsx(
            'mt-2 pt-2 border-t border-white/40 w-full flex items-center justify-center gap-1 text-[11px] font-medium hover:underline transition',
            sentiment.color
          )}
        >
          {t('sentiment.viewMore', { count: hiddenCount })}
          <ChevronRight className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}
