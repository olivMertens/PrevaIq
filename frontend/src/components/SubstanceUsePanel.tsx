'use client';

import { Cigarette, Wine, Cannabis, AlertCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';
import ConfidenceIndicator from './ConfidenceIndicator';
import clsx from 'clsx';
import { useState } from 'react';

interface SubstanceUsePanelProps {
  application: ApplicationMetadata;
}

interface SubstanceData {
  tobacco: { found: boolean; details: string; confidence?: number };
  alcohol: { found: boolean; details: string; confidence?: number };
  marijuana: { found: boolean; details: string; confidence?: number };
  drugs: { found: boolean; details: string; confidence?: number };
}

function parseSubstanceUse(application: ApplicationMetadata): SubstanceData {
  // Get confidence from underlying extracted fields (supports both English and French field names)
  const fields = application.extracted_fields || {};
  const smokingField = Object.values(fields).find(f => f.field_name === 'SmokingStatus' || f.field_name === 'StatutTabac');
  const alcoholField = Object.values(fields).find(f => f.field_name === 'AlcoholUse');
  const drugField = Object.values(fields).find(f => f.field_name === 'DrugUse');
  
  // First, try LLM outputs for lifestyle data
  const llmOtherFindings = application.llm_outputs?.medical_summary?.other_medical_findings?.parsed as any;
  const lifestyle = llmOtherFindings?.lifestyle;
  
  if (lifestyle) {
    const smokingStatus = lifestyle.smoking_status || '';
    const alcoholInfo = lifestyle.alcohol || '';
    // Use dedicated drug_use field; fall back to other only if it contains drug-related keywords
    const drugUseInfo = lifestyle.drug_use || '';
    const otherInfo = lifestyle.other || '';
    const drugKeywords = /cannabis|stup[eé]fiant|drogue|coca[iï]n|hero[iï]n|opiac|marijuana|thc|mdma|amphétamine|recreational|substance|controlled/i;
    const effectiveDrugInfo = drugUseInfo || (drugKeywords.test(otherInfo) ? otherInfo : '');
    
    const tobaccoFound = smokingStatus.length > 0 && 
      !smokingStatus.toLowerCase().includes('non-smoker') &&
      !smokingStatus.toLowerCase().includes('never');
    
    const alcoholFound = alcoholInfo.length > 0 && 
      !alcoholInfo.toLowerCase().includes('no alcohol') &&
      !alcoholInfo.toLowerCase().includes('none');
    
    const drugsFound = effectiveDrugInfo.length > 0 &&
      !effectiveDrugInfo.toLowerCase().includes('aucun') &&
      !effectiveDrugInfo.toLowerCase().includes('none');
    
    return {
      tobacco: { 
        found: tobaccoFound || smokingStatus.length > 0, 
        details: smokingStatus,
        confidence: smokingField?.confidence,
      },
      alcohol: { 
        found: alcoholFound || alcoholInfo.length > 0, 
        details: alcoholInfo,
        confidence: alcoholField?.confidence,
      },
      marijuana: { found: false, details: '' },
      drugs: { 
        found: drugsFound, 
        details: effectiveDrugInfo,
        confidence: drugField?.confidence,
      },
    };
  }
  
  // Fall back to extracted fields

  const tobaccoDetails = smokingField?.value ? String(smokingField.value) : '';
  const alcoholDetails = alcoholField?.value ? String(alcoholField.value) : '';
  const drugDetails = drugField?.value ? String(drugField.value) : '';

  // Check if tobacco use is present (look for keywords indicating use)
  const tobaccoFound = tobaccoDetails.length > 0 && 
    !tobaccoDetails.toLowerCase().includes('non-smoker') &&
    !tobaccoDetails.toLowerCase().includes('never');

  // Check if alcohol use is present
  const alcoholFound = alcoholDetails.length > 0 && 
    !alcoholDetails.toLowerCase().includes('no alcohol') &&
    !alcoholDetails.toLowerCase().includes('none');

  // Check if drug use is present
  const drugsFound = drugDetails.length > 0 && 
    !drugDetails.toLowerCase().includes('no ') &&
    !drugDetails.toLowerCase().includes('none');

  return {
    tobacco: { 
      found: tobaccoFound || tobaccoDetails.length > 0, 
      details: tobaccoDetails,
      confidence: smokingField?.confidence,
    },
    alcohol: { 
      found: alcoholFound || alcoholDetails.length > 0, 
      details: alcoholDetails,
      confidence: alcoholField?.confidence,
    },
    marijuana: { found: false, details: '' }, // No specific field for marijuana
    drugs: { 
      found: drugsFound || drugDetails.length > 0, 
      details: drugDetails,
      confidence: drugField?.confidence,
    },
  };
}

export default function SubstanceUsePanel({ application }: SubstanceUsePanelProps) {
  const [activeTab, setActiveTab] = useState<'tobacco' | 'alcohol' | 'marijuana' | 'drugs'>('tobacco');
  const t = useTranslations('substance');
  const substanceData = parseSubstanceUse(application);

  const tabs = [
    { id: 'tobacco' as const, label: t('tobacco'), icon: Cigarette, data: substanceData.tobacco },
    { id: 'alcohol' as const, label: t('alcohol'), icon: Wine, data: substanceData.alcohol },
    { id: 'marijuana' as const, label: t('cannabis'), icon: Cannabis, data: substanceData.marijuana },
    { id: 'drugs' as const, label: t('drugs'), icon: AlertCircle, data: substanceData.drugs },
  ];

  const activeData = tabs.find(t => t.id === activeTab)?.data;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 max-h-[400px] overflow-y-auto">
      {/* Tabs */}
      <div className="flex border-b border-slate-200 mb-4 sticky top-0 bg-white pb-0 -mt-2 pt-2 z-10">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={clsx(
              'flex flex-col items-center px-4 py-2 text-xs border-b-2 transition-colors',
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            )}
          >
            <tab.icon className="w-4 h-4 mb-1" />
            <span>{tab.label}</span>
            <span className="text-[10px] text-slate-400">
              {tab.data.found ? t('detected') : t('notDetected')}
            </span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="space-y-4">
        {activeData?.details ? (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <h4 className="text-sm font-medium text-slate-700">{t('extractedInfo')}</h4>
              {activeData.confidence !== undefined && (
                <ConfidenceIndicator 
                  confidence={activeData.confidence} 
                  fieldName={activeTab}
                />
              )}
            </div>
            <p className="text-sm text-slate-600 leading-relaxed">
              {activeData.details}
            </p>
          </div>
        ) : (
          <p className="text-sm text-slate-500 italic">
            {t('noInfo')}
          </p>
        )}
      </div>
    </div>
  );
}
