'use client';

import { User, Sparkles, Microscope } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata, PolicyCitation } from '@/lib/types';
import RiskRatingPopover from './RiskRatingPopover';

interface PatientSummaryProps {
  application: ApplicationMetadata;
  onPolicyClick?: (policyId: string) => void;
  onDeepDive?: () => void;
}

export default function PatientSummary({ application, onPolicyClick, onDeepDive }: PatientSummaryProps) {
  const t = useTranslations('patient');
  // Get summary from LLM outputs
  const customerProfile = application.llm_outputs?.application_summary?.customer_profile?.parsed as any;
  const summary = customerProfile?.summary || customerProfile?.medical_summary || null;
  const riskAssessment = customerProfile?.risk_assessment || null;
  const policyCitations: PolicyCitation[] = customerProfile?.policy_citations || [];
  const underwritingAction = customerProfile?.underwriting_action || null;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center">
            <User className="w-5 h-5 text-indigo-600" />
          </div>
          <h2 className="text-lg font-semibold text-slate-900">{t('summary')}</h2>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-600 border border-indigo-100">
            <Sparkles className="w-3 h-3" />
            {t('aiAnalysis')}
          </span>
        </div>

        {/* Risk Badge with Popover */}
        <div className="flex items-center gap-2">
          {(application.status === 'completed' || application.llm_outputs) && (
            <button
              onClick={onDeepDive}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-lg transition-colors"
            >
              <Microscope className="w-3.5 h-3.5" />
              {t('deepDive')}
            </button>
          )}
          {riskAssessment && (
            <RiskRatingPopover
            rating={riskAssessment}
            rationale={summary}
            citations={policyCitations}
            onPolicyClick={onPolicyClick}
          />
          )}
        </div>
      </div>

      {/* Summary Text */}
      {summary ? (
        <div className="space-y-4">
          <p className="text-sm text-slate-700 leading-relaxed">
            {summary}
          </p>
        </div>
      ) : (
        <p className="text-sm text-slate-500 italic">
          {t('noSummary')}
        </p>
      )}
    </div>
  );
}
