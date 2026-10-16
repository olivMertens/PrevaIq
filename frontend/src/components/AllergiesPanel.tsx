'use client';

import { AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';
import ConfidenceIndicator from './ConfidenceIndicator';

interface AllergiesPanelProps {
  application: ApplicationMetadata;
}

interface AllergiesData {
  allergies: string[];
  confidence?: number;
}

function parseAllergies(application: ApplicationMetadata): AllergiesData {
  const fields = application.extracted_fields || {};
  
  // Check for French field name from health underwriting analyzer
  const allergyField = Object.values(fields).find(f => 
    f.field_name === 'AllergiesConnues' || f.field_name === 'Allergies'
  );
  if (allergyField?.value) {
    const value = String(allergyField.value);
    const allergies = value.split(/[;,\n]/).map(s => s.trim()).filter(Boolean);
    return { allergies, confidence: allergyField.confidence };
  }
  
  // Check LLM outputs — other_medical_findings may have structured allergies
  const llmOther = (application as any).llm_outputs?.medical_summary?.other_medical_findings?.parsed;
  if (llmOther?.allergies && Array.isArray(llmOther.allergies) && llmOther.allergies.length > 0) {
    const allergies = llmOther.allergies.map((a: any) => {
      const parts = [a.allergen || a.name];
      if (a.reaction) parts.push(a.reaction);
      if (a.treatment) parts.push(a.treatment);
      return parts.join(' — ');
    }).filter(Boolean);
    if (allergies.length > 0) return { allergies };
  }
  // Also check conditions[] for allergy-related entries
  if (llmOther?.conditions && Array.isArray(llmOther.conditions)) {
    const allergyConditions = llmOther.conditions
      .filter((c: any) => /allergi/i.test(c.name || '') || /allergi/i.test(c.details || ''))
      .map((c: any) => `${c.name}${c.details ? ' — ' + c.details : ''}`);
    if (allergyConditions.length > 0) return { allergies: allergyConditions };
  }
  
  // Check medical conditions for allergies (English underwriting)
  const medicalField = Object.values(fields).find(f => f.field_name === 'MedicalConditionsSummary');
  if (!medicalField?.value) {
    return { allergies: [] };
  }

  const value = String(medicalField.value).toLowerCase();
  const allergies: string[] = [];

  // Look for allergy-related keywords
  const allergyPatterns = [
    /allerg\w*\s+to\s+([^;,]+)/gi,
    /([^;,]+)\s+allergy/gi,
    /allergic\s+to\s+([^;,]+)/gi,
  ];

  for (const pattern of allergyPatterns) {
    const matches = value.matchAll(pattern);
    for (const match of matches) {
      if (match[1]) {
        allergies.push(match[1].trim());
      }
    }
  }

  return { allergies, confidence: medicalField.confidence };
}

export default function AllergiesPanel({ application }: AllergiesPanelProps) {
  const t = useTranslations('allergies');
  const { allergies, confidence } = parseAllergies(application);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 bg-amber-100 rounded-lg flex items-center justify-center">
          <AlertTriangle className="w-5 h-5 text-amber-600" />
        </div>
        <h2 className="text-base font-semibold text-slate-900">{t('title')}</h2>
        {confidence !== undefined && (
          <ConfidenceIndicator confidence={confidence} fieldName="Allergies" />
        )}
      </div>

      {/* Content */}
      {allergies.length > 0 ? (
        <ul className="space-y-2">
          {allergies.map((allergy, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm text-slate-700">
              <span className="text-slate-400 mt-1">•</span>
              <span>{allergy}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex flex-col items-center justify-center py-4 text-center">
          <p className="text-sm text-slate-500 italic">{t('noAllergies')}</p>
        </div>
      )}
    </div>
  );
}
