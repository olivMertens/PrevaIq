'use client';

import React, { useMemo, useState, useCallback } from 'react';
import { CheckCircle, Edit3, XCircle, AlertTriangle, Zap, Clock, FileText, Phone, Send, ChevronDown, ShieldAlert } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations, useLocale } from 'next-intl';
import type { FraudAnalysisResponse } from '@/lib/api';

interface NextBestActionPanelProps {
  /** Extracted fields from the application */
  extractedFields: Record<string, unknown>;
  /** LLM analysis outputs */
  llmOutputs: Record<string, unknown>;
  /** Fraud analysis results (if available) */
  fraudResult: FraudAnalysisResponse | null;
  /** Total estimated amount */
  estimatedAmount: number;
  /** Whether AI analysis has been completed */
  analysisComplete: boolean;
  /** Callback when user validates the primary action */
  onValidate?: (action: string, justification: string) => void;
  /** Callback when user rejects */
  onReject?: (reason: string) => void;
}

interface RecommendedAction {
  id: string;
  label: string;
  icon: typeof Zap;
  confidence: number;
  reasoning: string;
  type: 'primary' | 'secondary';
  variant: 'approve' | 'request' | 'escalate' | 'deny' | 'payment';
}

export default function NextBestActionPanel({
  extractedFields,
  llmOutputs,
  fraudResult,
  estimatedAmount,
  analysisComplete,
  onValidate,
  onReject,
}: NextBestActionPanelProps) {
  const t = useTranslations('nextAction');
  const locale = useLocale();
  const numberLocale = locale === 'fr' ? 'fr-FR' : 'en-US';
  const [justification, setJustification] = useState('');
  const [showDetails, setShowDetails] = useState(false);
  const [actionTaken, setActionTaken] = useState<string | null>(null);

  // Compute recommended actions based on analysis state
  const actions = useMemo<RecommendedAction[]>(() => {
    if (!analysisComplete) return [];

    const fraudRisk = fraudResult?.overall_assessment?.risk_score ?? 0;
    const siuReferred = fraudResult?.overall_assessment?.siu_referral_recommended ?? false;
    const hasInconsistencies = fraudResult?.declaration_verification?.overall_consistent === false;

    // SIU referral — highest priority
    if (siuReferred) {
      return [
        {
          id: 'escalate_siu',
          label: t('labels.escalate_siu'),
          icon: ShieldAlert,
          confidence: 0.95,
          reasoning: fraudResult?.overall_assessment?.siu_referral_reason || t('reasoning.siu_default'),
          type: 'primary',
          variant: 'escalate',
        },
        {
          id: 'request_docs',
          label: t('labels.request_docs'),
          icon: FileText,
          confidence: 0.8,
          reasoning: t('reasoning.request_docs'),
          type: 'secondary',
          variant: 'request',
        },
        {
          id: 'call_client',
          label: t('labels.call_client'),
          icon: Phone,
          confidence: 0.6,
          reasoning: t('reasoning.call_client'),
          type: 'secondary',
          variant: 'request',
        },
      ];
    }

    // High fraud risk but no SIU referral
    if (fraudRisk > 0.6 || hasInconsistencies) {
      return [
        {
          id: 'request_expertise',
          label: t('labels.request_expertise'),
          icon: FileText,
          confidence: 0.85,
          reasoning: t('reasoning.request_expertise', { percent: Math.round(fraudRisk * 100) }),
          type: 'primary',
          variant: 'request',
        },
        {
          id: 'approve_partial',
          label: t('labels.approve_partial'),
          icon: CheckCircle,
          confidence: 0.5,
          reasoning: t('reasoning.approve_partial'),
          type: 'secondary',
          variant: 'approve',
        },
        {
          id: 'escalate_manager',
          label: t('labels.escalate_manager'),
          icon: AlertTriangle,
          confidence: 0.4,
          reasoning: t('reasoning.escalate_manager'),
          type: 'secondary',
          variant: 'escalate',
        },
      ];
    }

    // Low risk, high amount — needs expertise
    if (estimatedAmount > 5000 && fraudRisk < 0.3) {
      return [
        {
          id: 'approve_with_expertise',
          label: t('labels.approve_with_expertise'),
          icon: FileText,
          confidence: 0.9,
          reasoning: t('reasoning.approve_with_expertise', { amount: estimatedAmount.toLocaleString(numberLocale) }),
          type: 'primary',
          variant: 'request',
        },
        {
          id: 'approve_direct',
          label: t('labels.approve_direct'),
          icon: CheckCircle,
          confidence: 0.3,
          reasoning: t('reasoning.approve_direct'),
          type: 'secondary',
          variant: 'approve',
        },
      ];
    }

    // Standard low-risk case — can auto-approve (STP)
    if (fraudRisk < 0.3 && estimatedAmount <= 5000) {
      return [
        {
          id: 'stp_approve',
          label: t('labels.stp_approve'),
          icon: Zap,
          confidence: 0.95,
          reasoning: t('reasoning.stp_approve', { amount: estimatedAmount.toLocaleString(numberLocale) }),
          type: 'primary',
          variant: 'payment',
        },
        {
          id: 'manual_review',
          label: t('labels.manual_review'),
          icon: Clock,
          confidence: 0.3,
          reasoning: t('reasoning.manual_review'),
          type: 'secondary',
          variant: 'request',
        },
      ];
    }

    // Default — moderate case
    return [
      {
        id: 'approve_standard',
        label: t('labels.approve_standard'),
        icon: CheckCircle,
        confidence: 0.75,
        reasoning: t('reasoning.approve_standard'),
        type: 'primary',
        variant: 'approve',
      },
      {
        id: 'request_info',
        label: t('labels.request_info'),
        icon: FileText,
        confidence: 0.5,
        reasoning: t('reasoning.request_info'),
        type: 'secondary',
        variant: 'request',
      },
    ];
  }, [analysisComplete, fraudResult, estimatedAmount, llmOutputs, extractedFields, t, numberLocale]);

  const primaryAction = actions.find(a => a.type === 'primary');
  const secondaryActions = actions.filter(a => a.type === 'secondary');

  const handleValidate = useCallback(() => {
    if (primaryAction) {
      setActionTaken(primaryAction.id);
      onValidate?.(primaryAction.id, justification);
    }
  }, [primaryAction, justification, onValidate]);

  const handleReject = useCallback(() => {
    setActionTaken('rejected');
    onReject?.(justification);
  }, [justification, onReject]);

  const variantStyles: Record<string, { bg: string; hover: string; ring: string }> = {
    approve: { bg: 'bg-emerald-600', hover: 'hover:bg-emerald-700', ring: 'ring-emerald-300' },
    payment: { bg: 'bg-emerald-600', hover: 'hover:bg-emerald-700', ring: 'ring-emerald-300' },
    request: { bg: 'bg-amber-600', hover: 'hover:bg-amber-700', ring: 'ring-amber-300' },
    escalate: { bg: 'bg-rose-600', hover: 'hover:bg-rose-700', ring: 'ring-rose-300' },
    deny: { bg: 'bg-slate-600', hover: 'hover:bg-slate-700', ring: 'ring-slate-300' },
  };

  if (!analysisComplete || actions.length === 0) {
    return (
      <div className="border border-dashed border-slate-200 rounded-lg p-4 text-center text-sm text-slate-400">
        <Zap className="w-5 h-5 mx-auto mb-2 opacity-40" />
        {t('emptyState')}
      </div>
    );
  }

  if (actionTaken) {
    return (
      <div className={clsx(
        'rounded-lg p-4 border text-sm',
        actionTaken === 'rejected' ? 'bg-rose-50 border-rose-200' : 'bg-emerald-50 border-emerald-200'
      )}>
        <div className="flex items-center gap-2 mb-1">
          {actionTaken === 'rejected' ? (
            <XCircle className="w-4 h-4 text-rose-600" />
          ) : (
            <CheckCircle className="w-4 h-4 text-emerald-600" />
          )}
          <span className="font-medium text-slate-900">
            {actionTaken === 'rejected' ? t('actionRejected') : t('actionValidated')}
          </span>
          <span className="ml-auto text-xs text-slate-400">{new Date().toLocaleTimeString(numberLocale, { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
        {justification && (
          <p className="text-xs text-slate-600 mt-1">{t('justificationLabel')} {justification}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Primary action */}
      {primaryAction && (
        <div className={clsx(
          'rounded-lg border p-4',
          primaryAction.variant === 'escalate' ? 'bg-rose-50 border-rose-200' :
          primaryAction.variant === 'payment' ? 'bg-emerald-50 border-emerald-200' :
          primaryAction.variant === 'approve' ? 'bg-emerald-50 border-emerald-200' :
          'bg-amber-50 border-amber-200'
        )}>
          <div className="flex items-start gap-3">
            <div className={clsx(
              'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
              primaryAction.variant === 'escalate' ? 'bg-rose-100' :
              primaryAction.variant === 'payment' ? 'bg-emerald-100' :
              primaryAction.variant === 'approve' ? 'bg-emerald-100' :
              'bg-amber-100'
            )}>
              <primaryAction.icon className={clsx(
                'w-4 h-4',
                primaryAction.variant === 'escalate' ? 'text-rose-600' :
                primaryAction.variant === 'payment' ? 'text-emerald-600' :
                primaryAction.variant === 'approve' ? 'text-emerald-600' :
                'text-amber-600'
              )} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-semibold text-slate-900">{primaryAction.label}</span>
                <span className={clsx(
                  'text-[10px] font-bold uppercase px-1.5 py-0.5 rounded',
                  primaryAction.confidence >= 0.9 ? 'bg-emerald-100 text-emerald-700' :
                  primaryAction.confidence >= 0.7 ? 'bg-amber-100 text-amber-700' :
                  'bg-slate-100 text-slate-600'
                )}>
                  {Math.round(primaryAction.confidence * 100)}{t('confidenceSuffix')}
                </span>
                {primaryAction.variant === 'payment' && (
                  <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-600 text-white">STP</span>
                )}
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">{primaryAction.reasoning}</p>
            </div>
          </div>

          {/* Justification input */}
          <div className="mt-3">
            <input
              type="text"
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              placeholder={t('justificationPlaceholder')}
              className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
            />
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={handleValidate}
              className={clsx(
                'flex-1 flex items-center justify-center gap-1.5 px-4 py-2 text-white text-sm font-medium rounded-lg transition-all',
                variantStyles[primaryAction.variant].bg,
                variantStyles[primaryAction.variant].hover,
              )}
            >
              <CheckCircle className="w-4 h-4" />
              {t('validate')}
            </button>
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="px-3 py-2 text-sm text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <Edit3 className="w-4 h-4" />
            </button>
            <button
              onClick={handleReject}
              className="px-3 py-2 text-sm text-rose-600 bg-white border border-rose-200 rounded-lg hover:bg-rose-50 transition-colors"
            >
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Secondary actions (collapsible) */}
      {secondaryActions.length > 0 && (
        <div>
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 transition-colors mb-2"
          >
            <ChevronDown className={clsx('w-3 h-3 transition-transform', showDetails && 'rotate-180')} />
            {t('alternativesCount', { count: secondaryActions.length })}
          </button>
          {showDetails && (
            <div className="space-y-2">
              {secondaryActions.map((action) => (
                <button
                  key={action.id}
                  onClick={() => { setActionTaken(action.id); onValidate?.(action.id, justification); }}
                  className="w-full flex items-center gap-3 p-3 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-left transition-colors group"
                >
                  <action.icon className="w-4 h-4 text-slate-400 group-hover:text-slate-600 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm font-medium text-slate-700 group-hover:text-slate-900">{action.label}</span>
                    <p className="text-xs text-slate-400 mt-0.5">{action.reasoning}</p>
                  </div>
                  <span className="text-[10px] text-slate-400 font-medium">{Math.round(action.confidence * 100)}%</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
