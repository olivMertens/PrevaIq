'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { CheckCircle, Clock, Send, TriangleAlert, X, XCircle } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import { submitApplicationDecision, type ApplicationDecision } from '@/lib/api';
import { useToast } from '@/lib/ToastProvider';

export interface DecisionDraft {
  decision: ApplicationDecision;
  notes?: string;
  conditions?: string;
}

interface DecisionDialogProps {
  applicationId: string;
  open: boolean;
  /** Pre-filled from the AI recommendation; the user still reviews and confirms. */
  draft?: DecisionDraft | null;
  riskLevel?: string;
  onClose: () => void;
  onSubmitted: (decision: ApplicationDecision) => void;
}

const OPTIONS: Array<{ id: ApplicationDecision; Icon: typeof CheckCircle; active: string }> = [
  { id: 'approve', Icon: CheckCircle, active: 'border-emerald-500 bg-emerald-50 text-emerald-800' },
  { id: 'approve_with_conditions', Icon: TriangleAlert, active: 'border-amber-500 bg-amber-50 text-amber-900' },
  { id: 'defer', Icon: Clock, active: 'border-slate-500 bg-slate-100 text-slate-800' },
  { id: 'decline', Icon: XCircle, active: 'border-rose-500 bg-rose-50 text-rose-800' },
];

export default function DecisionDialog(props: DecisionDialogProps) {
  return props.open ? <DecisionForm {...props} /> : null;
}

/** Mounted on open, so every opening starts from the current draft. */
function DecisionForm({ applicationId, draft, riskLevel, onClose, onSubmitted }: DecisionDialogProps) {
  const t = useTranslations('caseCockpit.decision');
  const tDecisions = useTranslations('decisions');
  const { addToast } = useToast();
  const titleId = useId();
  const firstFieldRef = useRef<HTMLButtonElement>(null);
  const [decision, setDecision] = useState<ApplicationDecision | null>(draft?.decision ?? null);
  const [notes, setNotes] = useState(draft?.notes ?? '');
  const [conditions, setConditions] = useState(draft?.conditions ?? '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => firstFieldRef.current?.focus());
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  const submit = async () => {
    if (!decision) return;
    setSaving(true);
    try {
      await submitApplicationDecision(applicationId, {
        decision,
        notes: notes.trim() || undefined,
        conditions: decision === 'approve_with_conditions' ? conditions.trim() || undefined : undefined,
        risk_level: riskLevel,
      });
      addToast('success', tDecisions('decisionRecorded'));
      onSubmitted(decision);
      onClose();
    } catch {
      addToast('error', tDecisions('decisionError'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-lg rounded-xl bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 id={titleId} className="text-base font-semibold text-slate-900">{t('title')}</h2>
          <button type="button" onClick={onClose} aria-label={t('cancel')} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100">
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">
          {draft && <p className="rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-900">{t('prefilled')}</p>}
          <div role="radiogroup" aria-label={t('title')} className="grid grid-cols-2 gap-2">
            {OPTIONS.map(({ id, Icon, active }, index) => (
              <button
                key={id}
                ref={(decision ? id === decision : index === 0) ? firstFieldRef : undefined}
                type="button"
                role="radio"
                aria-checked={decision === id}
                onClick={() => setDecision(id)}
                className={clsx(
                  'flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm font-medium',
                  decision === id ? active : 'border-slate-200 text-slate-700 hover:bg-slate-50',
                )}
              >
                <Icon className="h-4 w-4 flex-shrink-0" aria-hidden />
                {tDecisions(id)}
              </button>
            ))}
          </div>
          {decision === 'approve_with_conditions' && (
            <label className="block text-sm">
              <span className="font-medium text-slate-700">{t('conditions')}</span>
              <textarea
                value={conditions}
                onChange={(event) => setConditions(event.target.value)}
                placeholder={tDecisions('conditionsPlaceholder')}
                className="mt-1 h-16 w-full resize-none rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </label>
          )}
          <label className="block text-sm">
            <span className="font-medium text-slate-700">{tDecisions('decisionNotes')}</span>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder={tDecisions('notesPlaceholder')}
              className="mt-1 h-20 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </label>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
            {t('cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!decision || saving}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            <Send className="h-4 w-4" aria-hidden />
            {saving ? t('saving') : tDecisions('submitDecision')}
          </button>
        </div>
      </div>
    </div>
  );
}
