'use client';

import { FileText, Clock, User, Euro } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';
import CitableValue from '../CitableValue';
import ConfidenceIndicator from '../ConfidenceIndicator';

interface ClaimsSummaryProps {
  application?: ApplicationMetadata;
}

export default function ClaimsSummary({ application }: ClaimsSummaryProps) {
  const t = useTranslations('claimsSummary');
  // Extract claim data from application or use defaults
  const extractedFields = application?.extracted_fields || {};
  const llmOutputs = application?.llm_outputs || {};
  
  // Get field values with citation data
  const claimNumberField = extractedFields.claim_number;
  const claimantField = extractedFields.claimant_name;
  const policyField = extractedFields.policy_number;
  const dateField = extractedFields.date_of_service;
  const chargesField = extractedFields.total_charges;

  const claimData = {
    claimNumber: String(claimNumberField?.value ?? application?.external_reference ?? 'N/A'),
    claimant: String(claimantField?.value ?? 'N/A'),
    policyNumber: String(policyField?.value ?? 'N/A'),
    dateOfService: String(dateField?.value ?? 'N/A'),
    totalCharges: String(chargesField?.value ?? 'N/A'),
    status: (llmOutputs as Record<string, unknown>)?.claim_summary
      ? t('statusUnderReview')
      : application?.status === 'completed' ? t('statusProcessed') : t('statusPending'),
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center">
          <FileText className="w-5 h-5 text-indigo-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{t('title')}</h2>
          <p className="text-sm text-slate-500">{t('claimNumberPrefix')}{claimData.claimNumber}</p>
        </div>
        <span className="ml-auto px-3 py-1 bg-amber-100 text-amber-700 rounded-full text-sm font-medium">
          {claimData.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 bg-slate-50 rounded-lg">
          <div className="flex items-center gap-2 text-slate-500 text-sm mb-1">
            <User className="w-4 h-4" />
            <span>{t('claimant')}</span>
          </div>
          <div className="flex items-center gap-2">
            <CitableValue
              value={claimData.claimant}
              citation={claimantField}
              className="font-medium text-slate-900"
            />
            {claimantField?.confidence && (
              <ConfidenceIndicator confidence={claimantField.confidence} fieldName="Claimant Name" />
            )}
          </div>
        </div>

        <div className="p-4 bg-slate-50 rounded-lg">
          <div className="flex items-center gap-2 text-slate-500 text-sm mb-1">
            <FileText className="w-4 h-4" />
            <span>{t('policyNumber')}</span>
          </div>
          <div className="flex items-center gap-2">
            <CitableValue
              value={claimData.policyNumber}
              citation={policyField}
              className="font-medium text-slate-900"
            />
            {policyField?.confidence && (
              <ConfidenceIndicator confidence={policyField.confidence} fieldName="Policy Number" />
            )}
          </div>
        </div>

        <div className="p-4 bg-slate-50 rounded-lg">
          <div className="flex items-center gap-2 text-slate-500 text-sm mb-1">
            <Clock className="w-4 h-4" />
            <span>{t('dateOfService')}</span>
          </div>
          <div className="flex items-center gap-2">
            <CitableValue
              value={claimData.dateOfService}
              citation={dateField}
              className="font-medium text-slate-900"
            />
            {dateField?.confidence && (
              <ConfidenceIndicator confidence={dateField.confidence} fieldName="Date of Service" />
            )}
          </div>
        </div>

        <div className="p-4 bg-slate-50 rounded-lg">
          <div className="flex items-center gap-2 text-slate-500 text-sm mb-1">
            <Euro className="w-4 h-4" />
            <span>{t('totalCharges')}</span>
          </div>
          <div className="flex items-center gap-2">
            <CitableValue
              value={claimData.totalCharges}
              citation={chargesField}
              className="font-medium text-slate-900"
            />
            {chargesField?.confidence && (
              <ConfidenceIndicator confidence={chargesField.confidence} fieldName="Total Charges" />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
