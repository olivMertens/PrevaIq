'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { applicationCurrency } from '@/lib/currency';
import type { ApplicationMetadata } from '@/lib/types';
import ClientSentimentPanel from '../ClientSentimentPanel';
import CommunicationGenerator from '../CommunicationGenerator';
import CustomerAffiliationBanner from '../CustomerAffiliationBanner';
import { severityFromSentiment } from '../sentimentTone';

interface CustomerTabProps {
  application: ApplicationMetadata;
  customerData: Record<string, unknown> | null;
  linkedCustomerId: string | null;
  claimNature: string;
  estimatedAmount: number;
  insuredName: string;
  claimReference: string;
  settlementAmount: string;
  decisionStatus: 'approved' | 'pending' | 'denied';
  suggestedAddress: string;
  suggestedPhone: string;
  suggestedEmail: string;
  onAffiliated: () => void;
}

/** Customer state of mind, Client 360 link and a message drafted in the right tone. */
export default function CustomerTab({
  application,
  customerData,
  linkedCustomerId,
  claimNature,
  estimatedAmount,
  insuredName,
  claimReference,
  settlementAmount,
  decisionStatus,
  suggestedAddress,
  suggestedPhone,
  suggestedEmail,
  onAffiliated,
}: CustomerTabProps) {
  const t = useTranslations('caseCockpit.customerTab');
  const severity = severityFromSentiment(application.sentiment_analysis);
  const [openedAt] = useState(() => Date.now());
  const daysSinceClaim = application.created_at
    ? Math.floor((openedAt - new Date(application.created_at).getTime()) / 86400000)
    : 0;

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('sentiment')}</h3>
        <p className="mb-3 text-sm text-slate-600">{t('estimateNotice')}</p>
        <ClientSentimentPanel
          customerData={customerData}
          claimNature={claimNature}
          estimatedAmount={estimatedAmount}
          currency={applicationCurrency(application)}
          daysSinceClaim={daysSinceClaim}
          backendSentiment={application.sentiment_analysis ?? null}
          mode="full"
        />
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t('message')}</h3>
        <p className="text-sm text-slate-600">{t('reviewDraft')}</p>
        <CommunicationGenerator
          applicationId={application.id}
          insuredName={insuredName}
          claimReference={claimReference}
          decisionStatus={decisionStatus}
          settlementAmount={settlementAmount}
          defaultTone={severity === 'critical' || severity === 'warning' ? 'empathetic' : 'standard'}
        />
        <details className="rounded-lg border border-slate-200 p-3">
          <summary className="cursor-pointer text-sm font-medium text-indigo-800">{t('callGuide')}</summary>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-700">
            {['acknowledge', 'confirm', 'nextStep'].map((step) => <li key={step}>{t(`call.${step}`)}</li>)}
          </ol>
        </details>
      </section>

      <details className="rounded-lg border border-slate-200 p-3 xl:col-span-2">
        <summary className="cursor-pointer text-sm font-medium text-slate-700">{t('client360')} — {linkedCustomerId ? t('openProfile') : t('linkProfile')}</summary>
        <div className="mt-3">
        {linkedCustomerId ? (
          <a href={`/customers/${linkedCustomerId}`} className="text-sm font-medium text-indigo-700 underline">{t('openProfile')}</a>
        ) : (
          <CustomerAffiliationBanner
            applicationId={application.id}
            suggestedName={insuredName}
            suggestedAddress={suggestedAddress}
            suggestedPhone={suggestedPhone}
            suggestedEmail={suggestedEmail}
            onAffiliated={onAffiliated}
          />
        )}
        </div>
      </details>
    </div>
  );
}
