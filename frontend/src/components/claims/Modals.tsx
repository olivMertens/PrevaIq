import React, { useState, useEffect } from 'react';
import { X, AlertCircle, CheckCircle, Euro } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export function Modal({ isOpen, onClose, title, children, footer }: ModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg overflow-hidden flex flex-col max-h-[90vh]">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
          <h3 className="font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 overflow-y-auto">
          {children}
        </div>
        {footer && (
          <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex justify-end gap-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

interface FinalDecisionModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialData: any;
  onConfirm: (decision: any) => void;
}

export function FinalDecisionModal({ isOpen, onClose, initialData, onConfirm }: FinalDecisionModalProps) {
  const t = useTranslations('claimsModals');
  const [decision, setDecision] = useState('Approve with Adjustment');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    if (isOpen && initialData) {
      setDecision(initialData.decision || 'Approve with Adjustment');
      setNotes(initialData.reviewer_notes || '');
    }
  }, [isOpen, initialData]);

  const handleConfirm = () => {
    onConfirm({ decision, notes });
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t('proposeFinalDecision')}
      footer={
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors">
            {t('cancel')}
          </button>
          <button onClick={handleConfirm} className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors shadow-sm">
            {t('submitDecision')}
          </button>
        </>
      }
    >
      <div className="space-y-6">
        <div className="bg-indigo-50 p-4 rounded-lg border border-indigo-100">
          <h4 className="text-sm font-medium text-indigo-900 mb-2">{t('paymentSummary')}</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-indigo-600 block text-xs">{t('totalBilled')}</span>
              <span className="font-semibold text-indigo-900">{initialData?.payment_summary?.total_billed || '$0.00'}</span>
            </div>
            <div>
              <span className="text-indigo-600 block text-xs">{t('totalAllowed')}</span>
              <span className="font-semibold text-indigo-900">{initialData?.payment_summary?.total_allowed || '$0.00'}</span>
            </div>
            <div>
              <span className="text-indigo-600 block text-xs">{t('planPays')}</span>
              <span className="font-semibold text-indigo-900">{initialData?.payment_summary?.plan_pays || '$0.00'}</span>
            </div>
            <div>
              <span className="text-indigo-600 block text-xs">{t('memberPays')}</span>
              <span className="font-semibold text-indigo-900">{initialData?.payment_summary?.member_pays || '$0.00'}</span>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('decision')}</label>
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value)}
            className="w-full rounded-lg border-slate-300 text-sm focus:ring-indigo-500 focus:border-indigo-500"
          >
            <option value="Approve">{t('approve')}</option>
            <option value="Approve with Adjustment">{t('approveWithAdjustment')}</option>
            <option value="Deny">{t('deny')}</option>
            <option value="Pend">{t('pendForInfo')}</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('reviewerNotes')}</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            className="w-full rounded-lg border-slate-300 text-sm focus:ring-indigo-500 focus:border-indigo-500"
            placeholder={t('notesPlaceholder')}
          />
        </div>
      </div>
    </Modal>
  );
}

interface LineItemOverrideModalProps {
  isOpen: boolean;
  onClose: () => void;
  lineItem: any;
  onConfirm: (override: any) => void;
}

export function LineItemOverrideModal({ isOpen, onClose, lineItem, onConfirm }: LineItemOverrideModalProps) {
  const t = useTranslations('claimsModals');
  const [action, setAction] = useState('Approve');
  const [allowedAmount, setAllowedAmount] = useState('');
  const [reason, setReason] = useState('');

  useEffect(() => {
    if (isOpen && lineItem) {
      setAction(lineItem.decision === 'Approve' ? 'Approve' : 'Deny');
      setAllowedAmount(lineItem.allowed?.replace('$', '') || '');
      setReason('');
    }
  }, [isOpen, lineItem]);

  const handleConfirm = () => {
    onConfirm({ 
      line: lineItem.line,
      action, 
      allowed: allowedAmount ? `$${allowedAmount}` : lineItem.allowed,
      reason 
    });
    onClose();
  };

  if (!lineItem) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t('overrideLine', { line: lineItem.line })}
      footer={
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors">
            {t('cancel')}
          </button>
          <button onClick={handleConfirm} className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors shadow-sm">
            {t('saveOverride')}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 text-sm">
          <div className="flex justify-between mb-1">
            <span className="text-slate-500">{t('code')}:</span>
            <span className="font-mono font-medium text-slate-900">{lineItem.code}</span>
          </div>
          <div className="flex justify-between mb-1">
            <span className="text-slate-500">{t('description')}:</span>
            <span className="font-medium text-slate-900 text-right truncate ml-4">{lineItem.desc}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">{t('billed')}:</span>
            <span className="font-medium text-slate-900">{lineItem.billed}</span>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('action')}</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setAction('Approve')}
              className={clsx(
                "px-3 py-2 text-sm font-medium rounded-lg border transition-all flex items-center justify-center gap-2",
                action === 'Approve' 
                  ? "bg-emerald-50 border-emerald-200 text-emerald-700 ring-1 ring-emerald-500" 
                  : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
              )}
            >
              <CheckCircle className="w-4 h-4" />
              {t('approve')}
            </button>
            <button
              type="button"
              onClick={() => setAction('Deny')}
              className={clsx(
                "px-3 py-2 text-sm font-medium rounded-lg border transition-all flex items-center justify-center gap-2",
                action === 'Deny' 
                  ? "bg-rose-50 border-rose-200 text-rose-700 ring-1 ring-rose-500" 
                  : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
              )}
            >
              <AlertCircle className="w-4 h-4" />
              {t('deny')}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('allowedAmount')}</label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <span className="text-slate-500 sm:text-sm">$</span>
            </div>
            <input
              type="text"
              value={allowedAmount}
              onChange={(e) => setAllowedAmount(e.target.value)}
              className="pl-7 w-full rounded-lg border-slate-300 text-sm focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="0.00"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('reasonForOverride')}</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            className="w-full rounded-lg border-slate-300 text-sm focus:ring-indigo-500 focus:border-indigo-500"
            placeholder={t('reasonPlaceholder')}
          />
        </div>
      </div>
    </Modal>
  );
}
