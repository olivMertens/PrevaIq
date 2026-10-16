'use client';

import { Search } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';
import { extractPatientInfo, calculateBMI, getCitations } from '@/lib/api';
import ConfidenceIndicator from './ConfidenceIndicator';
import CitationTooltip from './CitationTooltip';
import StatusBadge from './landing/StatusBadge';

interface PatientHeaderProps {
  application: ApplicationMetadata;
}

export default function PatientHeader({ application }: PatientHeaderProps) {
  const t = useTranslations('patient');
  const patient = extractPatientInfo(application);
  
  // Get citations for patient fields
  const citations = getCitations(application, [
    'ApplicantName',
    'Occupation', 
    'Weight',
    'DateOfBirth',
    'Age',
    'Gender',
    'Height',
  ]);
  
  // Try to get key fields from LLM customer profile
  const customerProfile = application.llm_outputs?.application_summary?.customer_profile?.parsed as any;
  const keyFields = customerProfile?.key_fields as Array<{label: string; value: string}> | undefined;
  
  // Helper to get LLM field value
  const getLlmField = (label: string): string | undefined => {
    return keyFields?.find(f => f.label.toLowerCase() === label.toLowerCase())?.value;
  };
  
  // Calculate BMI if not provided
  const bmi = patient.bmi !== 'N/A' 
    ? patient.bmi 
    : calculateBMI(patient.height, patient.weight) || 'N/A';

  // Helper to check if we have meaningful data
  const hasValue = (val: string | number) => val !== 'N/A' && val !== '';

  // Helper to build citation data for tooltip
  const buildCitation = (fieldName: string) => {
    const field = citations[fieldName];
    if (!field) return undefined;
    return {
      sourceFile: field.source_file,
      pageNumber: field.page_number,
      sourceText: field.source_text,
    };
  };

  return (
    <header className="bg-white border-b border-slate-200 px-6 py-4">
      <div className="flex items-center justify-between">
        {/* Patient Name and Application Info */}
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-bold text-slate-900">
            {hasValue(patient.name) ? (
              application.external_reference ? (
                <a href={`/customers/${application.external_reference}`} className="hover:text-indigo-600 transition-colors cursor-pointer">
                  {patient.name}
                </a>
              ) : patient.name
            ) : `Application ${application.id}`}
          </h1>
          {application.external_reference && (
            <>
              <span className="text-lg text-slate-600">-</span>
              <a href={`/customers/${application.external_reference}`} className="text-lg font-medium text-blue-600 hover:text-blue-800 hover:underline transition-colors">
                {application.external_reference}
              </a>
            </>
          )}
          <span className="ml-2">
            <StatusBadge status={application.status} processingStatus={application.processing_status} />
          </span>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder={t('searchPlaceholder')}
            className="pl-9 pr-4 py-2 w-64 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Patient Details Row - only show if we have data */}
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 mt-4 text-sm">
        {hasValue(patient.name) && (
          <div className="flex items-center gap-2">
            <span className="text-slate-500">{t('name')}</span>
            <span className="font-medium text-slate-900">{patient.name}</span>
            {citations.ApplicantName?.confidence !== undefined && (
              <ConfidenceIndicator confidence={citations.ApplicantName.confidence} fieldName="Name" />
            )}
            {buildCitation('ApplicantName') && (
              <CitationTooltip citation={buildCitation('ApplicantName')!} appId={application.id}>
                <span></span>
              </CitationTooltip>
            )}
          </div>
        )}
        {hasValue(patient.occupation) && (
          <div className="flex items-center gap-2">
            <span className="text-slate-500">{t('occupation')}</span>
            <span className="font-medium text-slate-900">{patient.occupation}</span>
            {citations.Occupation?.confidence !== undefined && (
              <ConfidenceIndicator confidence={citations.Occupation.confidence} fieldName="Occupation" />
            )}
            {buildCitation('Occupation') && (
              <CitationTooltip citation={buildCitation('Occupation')!} appId={application.id}>
                <span></span>
              </CitationTooltip>
            )}
          </div>
        )}
        {hasValue(patient.weight) && (
          <div className="flex items-center gap-2">
            <span className="text-slate-500">{t('weight')}</span>
            <span className="font-medium text-slate-900">{patient.weight}</span>
            {citations.Weight?.confidence !== undefined && (
              <ConfidenceIndicator confidence={citations.Weight.confidence} fieldName="Weight" />
            )}
            {buildCitation('Weight') && (
              <CitationTooltip citation={buildCitation('Weight')!} appId={application.id}>
                <span></span>
              </CitationTooltip>
            )}
          </div>
        )}
        {hasValue(patient.dateOfBirth) && (
          <div className="flex items-center gap-2">
            <span className="text-slate-500">{t('dob')}</span>
            <span className="font-medium text-slate-900">{patient.dateOfBirth}</span>
            {hasValue(patient.age) && (
              <span className="text-xs text-slate-400">({patient.age} {t('age')})</span>
            )}
            {citations.DateOfBirth?.confidence !== undefined && (
              <ConfidenceIndicator confidence={citations.DateOfBirth.confidence} fieldName="Date of Birth" />
            )}
            {buildCitation('DateOfBirth') && (
              <CitationTooltip citation={buildCitation('DateOfBirth')!} appId={application.id}>
                <span></span>
              </CitationTooltip>
            )}
          </div>
        )}
        {hasValue(patient.gender) && (
          <div className="flex items-center gap-2">
            <span className="text-slate-500">{t('gender')}</span>
            <span className="font-medium text-slate-900">{patient.gender}</span>
            {citations.Gender?.confidence !== undefined && (
              <ConfidenceIndicator confidence={citations.Gender.confidence} fieldName="Gender" />
            )}
            {buildCitation('Gender') && (
              <CitationTooltip citation={buildCitation('Gender')!} appId={application.id}>
                <span></span>
              </CitationTooltip>
            )}
          </div>
        )}
        {hasValue(String(bmi)) && (
          <div className="flex items-center gap-2">
            <span className="text-slate-500">{t('bmi')}</span>
            <span className="font-medium text-slate-900">{bmi}</span>
          </div>
        )}
        {hasValue(patient.height) && (
          <div className="flex items-center gap-2">
            <span className="text-slate-500">{t('height')}</span>
            <span className="font-medium text-slate-900">{patient.height}</span>
            {citations.Height?.confidence !== undefined && (
              <ConfidenceIndicator confidence={citations.Height.confidence} fieldName="Height" />
            )}
            {buildCitation('Height') && (
              <CitationTooltip citation={buildCitation('Height')!} appId={application.id}>
                <span></span>
              </CitationTooltip>
            )}
          </div>
        )}
      </div>

      {/* Show message if no patient data */}
      {!hasValue(patient.name) && !hasValue(patient.dateOfBirth) && (
        <p className="mt-4 text-sm text-slate-500 italic">
          {t('informationNotExtracted')}
        </p>
      )}
    </header>
  );
}
