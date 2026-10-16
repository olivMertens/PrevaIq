'use client';

import { useState } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Clock, MessageSquare, Send } from 'lucide-react';
import { useTranslations } from 'next-intl';
import clsx from 'clsx';
import { useToast } from '@/lib/ToastProvider';

type DecisionType = 'approve' | 'approve_with_conditions' | 'defer' | 'decline' | null;

interface Props {
  applicationId: string;
  riskLevel?: string;
  hasBlockingFindings?: boolean;
  onDecisionSubmitted?: (decision: DecisionType) => void;
  position?: 'top' | 'bottom';
}

const buttons = [
  { id: 'approve' as const, Icon: CheckCircle, active: 'bg-emerald-600 text-white ring-2 ring-emerald-300', idle: 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100', canBlock: true },
  { id: 'approve_with_conditions' as const, Icon: AlertTriangle, active: 'bg-amber-500 text-white ring-2 ring-amber-300', idle: 'bg-amber-50 text-amber-700 hover:bg-amber-100', canBlock: false },
  { id: 'defer' as const, Icon: Clock, active: 'bg-slate-600 text-white ring-2 ring-slate-300', idle: 'bg-slate-100 text-slate-600 hover:bg-slate-200', canBlock: false },
  { id: 'decline' as const, Icon: XCircle, active: 'bg-red-600 text-white ring-2 ring-red-300', idle: 'bg-red-50 text-red-700 hover:bg-red-100', canBlock: false },
];

const submittedStyles: Record<string, { bg: string; text: string; Icon: typeof CheckCircle }> = {
  approve: { bg: 'bg-emerald-50', text: 'text-emerald-700', Icon: CheckCircle },
  approve_with_conditions: { bg: 'bg-amber-50', text: 'text-amber-700', Icon: AlertTriangle },
  defer: { bg: 'bg-slate-100', text: 'text-slate-700', Icon: Clock },
  decline: { bg: 'bg-red-50', text: 'text-red-700', Icon: XCircle },
};

export default function UnderwritingDecisionFooter({
  applicationId,
  riskLevel,
  hasBlockingFindings = false,
  onDecisionSubmitted,
  position = 'bottom',
}: Props) {
  const t = useTranslations('decisions');
  const { addToast } = useToast();
  const [decision, setDecision] = useState<DecisionType>(null);
  const [notes, setNotes] = useState('');
  const [conditions, setConditions] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async () => {
    if (!decision) return;
    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/applications/${applicationId}/decision`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          notes: notes || undefined,
          conditions: decision === 'approve_with_conditions' ? conditions : undefined,
          risk_level: riskLevel,
        }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      setSubmitted(true);
      addToast('success', t('decisionRecorded'));
      onDecisionSubmitted?.(decision);
    } catch {
      addToast('error', t('decisionError'));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted && decision) {
    const style = submittedStyles[decision];
    const SubmittedIcon = style.Icon;
    return (
      <div className={clsx('bg-white px-6 py-4 z-20', position === 'top' ? 'border-b border-slate-200 shadow-sm sticky top-0' : 'border-t border-slate-200')}>
        <div className={`flex items-center gap-3 px-4 py-3 rounded-lg ${style.bg}`}>
          <SubmittedIcon className={`w-5 h-5 ${style.text}`} />
          <span className={`font-medium ${style.text}`}>
            {t('decisionSubmitted', { decision: t(decision) })}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className={clsx('bg-white px-6 py-4 space-y-3 flex-shrink-0 z-20', position === 'top' ? 'border-b border-slate-200 shadow-sm sticky top-0' : 'border-t border-slate-200')}>
      {/* Decision buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium text-slate-600 mr-2">{t('yourDecision')}</span>
        {buttons.map(({ id, Icon, active, idle, canBlock }) => {
          const disabled = canBlock && hasBlockingFindings;
          return (
            <button
              key={id}
              onClick={() => !disabled && setDecision(id)}
              disabled={disabled}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                decision === id ? active : disabled ? 'bg-slate-100 text-slate-400 cursor-not-allowed' : idle
              }`}
              title={disabled ? t('blockingIssues') : ''}
            >
              <Icon className="w-4 h-4" />
              {t(id)}
            </button>
          );
        })}
      </div>

      {/* Conditions input */}
      {decision === 'approve_with_conditions' && (
        <textarea
          value={conditions}
          onChange={(e) => setConditions(e.target.value)}
          placeholder={t('conditionsPlaceholder')}
          className="w-full h-12 px-3 py-2 text-sm border border-amber-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-amber-400 bg-amber-50"
        />
      )}

      {/* Notes + Submit */}
      {decision && (
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <MessageSquare className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-xs text-slate-500">{t('decisionNotes')}</span>
            </div>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t('notesPlaceholder')}
              className="w-full h-14 px-3 py-2 text-sm border border-slate-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="self-end flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors font-medium"
          >
            <Send className="w-4 h-4" />
            {t('submitDecision')}
          </button>
        </div>
      )}

      {/* Blocking issues warning */}
      {hasBlockingFindings && (
        <div className="flex items-center gap-2 text-xs text-red-600">
          <AlertTriangle className="w-3.5 h-3.5" />
          {t('blockingIssuesWarning')}
        </div>
      )}
    </div>
  );
}
