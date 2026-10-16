'use client';

import { CheckCircle2, XCircle, AlertTriangle, Shield } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';

interface EligibilityCheck {
  id: number;
  check: string;
  status: 'pass' | 'fail' | 'warning';
  details: string;
}

interface EligibilityPanelProps {
  application?: ApplicationMetadata;
}

export default function EligibilityPanel({ application }: EligibilityPanelProps) {
  const t = useTranslations('eligibility');
  // Extract eligibility checks from application or use sample data
  const extractedFields = application?.extracted_fields || {};
  
  // Default sample eligibility checks if no application data
  const defaultChecks: EligibilityCheck[] = [
    {
      id: 1,
      check: 'Policy Active at Date of Loss',
      status: 'pass',
      details: 'Policy effective 01/01/2024 - Present',
    },
    {
      id: 2,
      check: 'Waiting Period Satisfied',
      status: 'pass',
      details: '90-day waiting period completed on 04/01/2024',
    },
    {
      id: 3,
      check: 'Pre-existing Condition Exclusion',
      status: 'warning',
      details: 'Reviewing medical history for related conditions',
    },
    {
      id: 4,
      check: 'Coverage Limit Available',
      status: 'pass',
      details: '$50,000 remaining of $100,000 annual maximum',
    },
    {
      id: 5,
      check: 'Deductible Status',
      status: 'pass',
      details: '$500 deductible met for current policy year',
    },
  ];

  const eligibilityChecks: EligibilityCheck[] = Array.isArray(extractedFields.eligibility_checks?.value)
    ? extractedFields.eligibility_checks.value as EligibilityCheck[]
    : defaultChecks;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pass':
        return <CheckCircle2 className="w-5 h-5 text-emerald-500" />;
      case 'fail':
        return <XCircle className="w-5 h-5 text-rose-500" />;
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      default:
        return null;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pass':
        return 'border-emerald-200 bg-emerald-50/50';
      case 'fail':
        return 'border-rose-200 bg-rose-50/50';
      case 'warning':
        return 'border-amber-200 bg-amber-50/50';
      default:
        return 'border-slate-200';
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center">
          <Shield className="w-5 h-5 text-indigo-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{t('title')}</h2>
          <p className="text-sm text-slate-500">{t('subtitle')}</p>
        </div>
      </div>

      <div className="space-y-3">
        {eligibilityChecks.map((check) => (
          <div
            key={check.id}
            className={`p-4 border rounded-lg ${getStatusColor(check.status)}`}
          >
            <div className="flex items-start gap-3">
              {getStatusIcon(check.status)}
              <div className="flex-1">
                <h4 className="font-medium text-slate-900">{check.check}</h4>
                <p className="text-sm text-slate-600 mt-0.5">{check.details}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="mt-6 p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-emerald-600" />
          <span className="font-medium text-emerald-900">
            {t('preliminaryApproved')}
          </span>
        </div>
        <p className="text-sm text-emerald-700 mt-1 ml-7">
          {t('checksSummary', {
            passed: eligibilityChecks.filter(c => c.status === 'pass').length,
            total: eligibilityChecks.length,
            review: eligibilityChecks.filter(c => c.status !== 'pass').length
          })}
        </p>
      </div>
    </div>
  );
}
