'use client';

import { Stethoscope, Calendar, Building2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';

interface MedicalRecord {
  id: number;
  date: string;
  provider: string;
  type: string;
  diagnosis: string;
  icdCode?: string;
  cptCode?: string;
  notes?: string;
}

interface MedicalRecordsPanelProps {
  application?: ApplicationMetadata;
}

export default function MedicalRecordsPanel({ application }: MedicalRecordsPanelProps) {
  const t = useTranslations('medicalRecords');
  // Extract medical records from application or use sample data
  const extractedFields = application?.extracted_fields || {};
  
  // Default sample records if no application data
  const defaultRecords: MedicalRecord[] = [
    {
      id: 1,
      date: '2024-11-15',
      provider: 'City General Hospital',
      type: 'Emergency Room Visit',
      diagnosis: 'Acute appendicitis',
      icdCode: 'K35.80',
    },
    {
      id: 2,
      date: '2024-11-16',
      provider: 'City General Hospital',
      type: 'Surgical Procedure',
      diagnosis: 'Laparoscopic appendectomy',
      cptCode: '44970',
    },
    {
      id: 3,
      date: '2024-11-18',
      provider: 'City General Hospital',
      type: 'Hospital Discharge',
      diagnosis: 'Post-operative recovery - uncomplicated',
      notes: 'Patient discharged in stable condition',
    },
  ];
  
  const records: MedicalRecord[] = Array.isArray(extractedFields.medical_records?.value) 
    ? extractedFields.medical_records.value as MedicalRecord[]
    : defaultRecords;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center">
          <Stethoscope className="w-5 h-5 text-indigo-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{t('title')}</h2>
          <p className="text-sm text-slate-500">{t('recordsFound', { count: records.length })}</p>
        </div>
      </div>

      <div className="space-y-4">
        {records.map((record) => (
          <div
            key={record.id}
            className="p-4 border border-slate-200 rounded-lg hover:border-indigo-300 transition-colors"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded text-xs font-medium">
                    {record.type}
                  </span>
                  {record.icdCode && (
                    <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-xs">
                      ICD: {record.icdCode}
                    </span>
                  )}
                  {record.cptCode && (
                    <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-xs">
                      CPT: {record.cptCode}
                    </span>
                  )}
                </div>
                <h4 className="font-medium text-slate-900">{record.diagnosis}</h4>
                {record.notes && (
                  <p className="text-sm text-slate-500 mt-1">{record.notes}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-4 mt-3 text-sm text-slate-500">
              <div className="flex items-center gap-1">
                <Calendar className="w-4 h-4" />
                <span>{record.date}</span>
              </div>
              <div className="flex items-center gap-1">
                <Building2 className="w-4 h-4" />
                <span>{record.provider}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}
