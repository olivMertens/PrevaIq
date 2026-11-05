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
  decisionStatus: 'approved' | 'pending';
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
    <div className="space-y-6">
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('sentiment')}</h3>
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

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('client360')}</h3>
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
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('message')}</h3>
        <CommunicationGenerator
          applicationId={application.id}
          insuredName={insuredName}
          claimReference={claimReference}
          decisionStatus={decisionStatus}
          settlementAmount={settlementAmount}
          defaultTone={severity === 'critical' || severity === 'warning' ? 'empathetic' : 'standard'}
        />
      </section>
    </div>
  );
}
