'use client';

import { useTranslations } from 'next-intl';
import { CockpitCard } from './caseUi';

export interface CaseFact {
  label: string;
  value: string;
  href?: string;
}

interface CaseFactsProps {
  facts: CaseFact[];
  fieldCount: number;
  linkedCustomerId?: string | null;
  onOpenData: () => void;
  onOpenCustomer: () => void;
}

/** The few identity facts a handler checks first; every other field lives in the drawer. */
export default function CaseFacts({ facts, fieldCount, linkedCustomerId, onOpenData, onOpenCustomer }: CaseFactsProps) {
  const t = useTranslations('caseCockpit.facts');
  return (
    <CockpitCard
      title={t('title')}
      headingId="cockpit-facts"
      aside={
        fieldCount > 0 ? (
          <button type="button" onClick={onOpenData} className="text-sm font-medium text-indigo-700 hover:underline">
            {t('allFields', { count: fieldCount })}
          </button>
        ) : undefined
      }
    >
      <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5 px-4 py-3 text-sm">
        {facts.map((fact) => (
          <div key={fact.label} className="contents">
            <dt className="text-slate-500">{fact.label}</dt>
            <dd className="min-w-0 truncate text-slate-900" title={fact.value}>
              {fact.href ? <a href={fact.href} className="text-indigo-700 underline">{fact.value}</a> : fact.value}
            </dd>
          </div>
        ))}
        <dt className="text-slate-500">{t('client360')}</dt>
        <dd>
          {linkedCustomerId ? (
            <a href={`/customers/${linkedCustomerId}`} className="text-indigo-700 underline">{t('linked')}</a>
          ) : (
            <>
              <span className="text-amber-800">{t('notLinked')}</span>
              {' · '}
              <button type="button" onClick={onOpenCustomer} className="font-medium text-indigo-700 underline">{t('link')}</button>
            </>
          )}
        </dd>
      </dl>
    </CockpitCard>
  );
}
