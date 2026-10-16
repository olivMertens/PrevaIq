'use client';

import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';
import { FieldWithConfidence, getFieldData } from './lifeHealthHelpers';

interface HeaderStripProps {
  application: ApplicationMetadata | null;
}

export default function LifeHealthHeaderStrip({ application }: HeaderStripProps) {
  const t = useTranslations('lifeHealth');
  const extractedFields = application?.extracted_fields || {};
  const llmOutputs = (application?.llm_outputs || {}) as Record<string, any>;

  const eligibility = (llmOutputs.benefits_policy?.eligibility_verification?.parsed || {}) as Record<string, any>;
  const planDetails = eligibility.plan_details || {};
  const coverageDatesObj = eligibility.coverage_dates || {};
  const llmPlanName = planDetails.plan_name;
  const llmCoverageDates = coverageDatesObj.effective_date && coverageDatesObj.termination_date
    ? `${coverageDatesObj.effective_date} - ${coverageDatesObj.termination_date}`
    : '';

  const finalDecision = (llmOutputs.tasks_decisions?.final_decision?.parsed || {}) as Record<string, any>;
  const paymentSummary = finalDecision.payment_summary || {};

  const timelineEvents = (llmOutputs.clinical_timeline?.treatment_timeline?.parsed?.timeline_events || []) as any[];
  const officeVisit = timelineEvents.find((e: any) => e.event_type === 'Office Visit' || e.event_type === 'Visit');
  const llmProviderName = officeVisit?.provider || '';

  const planNameData = getFieldData(extractedFields, ['PlanName', 'plan_name', 'policy_number'], llmPlanName || 'N/A');
  const coverageDatesData = getFieldData(extractedFields, ['CoverageDates', 'coverage_dates', 'date_of_service'], llmCoverageDates || 'N/A');
  const providerNameData = getFieldData(extractedFields, ['ProviderName', 'provider_name'], llmProviderName || 'N/A');
  const billedAmountData = getFieldData(extractedFields, ['BilledAmount', 'total_charges', 'billed_amount'], paymentSummary.total_billed || 'N/A');
  const allowedAmountData = getFieldData(extractedFields, ['AllowedAmount', 'allowed_amount'], paymentSummary.total_allowed || 'N/A');
  const planLiabilityData = getFieldData(extractedFields, ['PlanLiability', 'plan_liability', 'plan_pays'], paymentSummary.plan_pays || 'N/A');
  const memberOOPData = getFieldData(extractedFields, ['MemberOOP', 'member_oop', 'member_responsibility'], paymentSummary.member_pays || 'N/A');

  return (
    <div className="bg-gradient-to-r from-indigo-600 to-indigo-700 text-white px-5 py-2.5 flex-shrink-0">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-indigo-200 text-xs">{t('policyLabel')}</span>
            <FieldWithConfidence data={planNameData} className="font-medium" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-indigo-200 text-xs">{t('coverageLabel')}</span>
            <FieldWithConfidence data={coverageDatesData} className="font-medium" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-indigo-200 text-xs">{t('providerLabel')}</span>
            <FieldWithConfidence data={providerNameData} className="font-medium" />
          </div>
        </div>
        <div className="flex items-center gap-5">
          <div className="text-center">
            <div className="text-xs text-indigo-200">{t('billed')}</div>
            <div className="flex justify-center"><FieldWithConfidence data={billedAmountData} className="font-semibold" formatAsMoney /></div>
          </div>
          <div className="text-center">
            <div className="text-xs text-indigo-200">{t('allowed')}</div>
            <div className="flex justify-center"><FieldWithConfidence data={allowedAmountData} className="font-semibold" formatAsMoney /></div>
          </div>
          <div className="text-center">
            <div className="text-xs text-indigo-200">{t('planPays')}</div>
            <div className="flex justify-center"><FieldWithConfidence data={planLiabilityData} className="font-semibold text-emerald-300" formatAsMoney /></div>
          </div>
          <div className="text-center">
            <div className="text-xs text-indigo-200">{t('memberOOP')}</div>
            <div className="flex justify-center"><FieldWithConfidence data={memberOOPData} className="font-semibold" formatAsMoney /></div>
          </div>
          <span className="px-2.5 py-1 bg-rose-500 rounded-full text-xs font-medium">{t('riskHigh')}</span>
        </div>
      </div>
    </div>
  );
}
