'use client';

import React, { useState, useRef } from 'react';
import { Mail, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';
import CommunicationGenerator from './CommunicationGenerator';
import { Severity, toneForSeverity } from './sentimentTone';

interface CommunicationClientPanelProps {
  applicationId: string;
  insuredName: string;
  claimReference: string;
  decisionStatus?: 'approved' | 'pending' | 'denied' | 'investigation' | null;
  settlementAmount?: string;
  /** Board type label shown in the banner, e.g. "Habitation MRH", "Auto", "Santé" */
  boardLabel?: string;
  /**
   * AI-driven client sentiment severity — drives the banner accent color so a
   * calm/normal client doesn't see an alarming red CTA. Defaults to "normal"
   * which falls back to a brand-neutral palette.
   */
  severity?: Severity;
}

export default function CommunicationClientPanel({
  applicationId,
  insuredName,
  claimReference,
  decisionStatus,
  settlementAmount,
  boardLabel,
  severity = 'normal',
}: CommunicationClientPanelProps) {
  const t = useTranslations('claims');
  const tActions = useTranslations('communicationActions');
  const [dialogOpen, setDialogOpen] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
      setDialogOpen(false);
    }
  };

  // Sentiment-driven accent (replaces the previous brand-only ternary).
  const tone = toneForSeverity(severity);

  // Map severity to the recommended communication tone so the dropdown
  // pre-selects 'Empathique' for stressed/critical clients.
  const defaultCommTone: 'empathetic' | 'standard' | 'formal' =
    severity === 'critical' || severity === 'warning' ? 'empathetic' : 'standard';

  return (
    <>
      {/* Compact inline trigger bar — mirrors FraudAnalysisPanel pattern */}
      <div className="border-t border-slate-200 px-4 py-2.5 bg-slate-50">
        <div className="flex items-center gap-3">
          <Mail className={`w-4 h-4 ${tone.iconColor} flex-shrink-0`} />
          <span className="text-sm font-medium text-slate-700">{t('panels.clientCommunication')}</span>
          {boardLabel && (
            <span className="ml-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-500 border border-slate-200">
              {boardLabel}
            </span>
          )}
          {severity !== 'normal' && (
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${tone.badgeBg} ${tone.badgeText}`}>
              {tone.label}
            </span>
          )}
          <button
            onClick={() => setDialogOpen(true)}
            className={`ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${tone.buttonClass}`}
          >
            <Mail className="w-3.5 h-3.5" />
            {tActions('generateCommunication')}
          </button>
        </div>
      </div>

      {/* Dialog overlay */}
      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={handleBackdropClick}>
          <div ref={dialogRef} className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden mx-4">
            {/* Dialog header */}
            <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-3 flex-shrink-0 bg-slate-50">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-slate-100">
                <Mail className={`w-4 h-4 ${tone.iconColor}`} />
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-slate-900">{t('panels.clientCommunication')}</h3>
                {boardLabel && <p className="text-[11px] text-slate-500 truncate">{boardLabel} — {brand.name}</p>}
              </div>
              {severity !== 'normal' && (
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${tone.badgeBg} ${tone.badgeText}`}>
                  {tone.label}
                </span>
              )}
              <button onClick={() => setDialogOpen(false)} title={tActions('close')} className="ml-auto p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Communication generator body */}
            <div className="flex-1 overflow-auto p-5">
              <CommunicationGenerator
                applicationId={applicationId}
                insuredName={insuredName}
                claimReference={claimReference}
                decisionStatus={decisionStatus}
                settlementAmount={settlementAmount}
                defaultTone={defaultCommTone}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
