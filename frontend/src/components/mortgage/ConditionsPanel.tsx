'use client';

import { CheckCircle, AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { MortgageFinding } from './types';

export default function ConditionsPanel({ findings }: { findings: MortgageFinding[] }) {
  const t = useTranslations('mortgageLabels');
  const failedFindings = findings.filter(f => f.severity === 'fail' || f.severity === 'warning');

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-900 mb-4">{t('conditionsStipulations')}</h3>
        {failedFindings.length === 0 ? (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="flex items-center gap-2 text-green-700">
              <CheckCircle className="w-5 h-5" />
              <span className="font-medium">{t('noConditions')}</span>
            </div>
            <p className="text-sm text-green-600 mt-1">
              {t('allChecksPassed')}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {failedFindings.map((finding) => (
              <div
                key={finding.rule_id}
                className={`border rounded-lg p-4 ${
                  finding.severity === 'fail'
                    ? 'border-red-200 bg-red-50'
                    : 'border-amber-200 bg-amber-50'
                }`}
              >
                <div className="flex items-start gap-3">
                  <AlertTriangle
                    className={`w-5 h-5 mt-0.5 ${
                      finding.severity === 'fail' ? 'text-red-500' : 'text-amber-500'
                    }`}
                  />
                  <div className="flex-1">
                    <p className={`font-medium ${
                      finding.severity === 'fail' ? 'text-red-700' : 'text-amber-700'
                    }`}>
                      {finding.message}
                    </p>
                    <p className="text-sm text-slate-600 mt-1">
                      {t('ruleLabel')}: {finding.rule_id} • {t('categoryLabel')}: {finding.category}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
