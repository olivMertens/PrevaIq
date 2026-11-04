'use client';

import clsx from 'clsx';
import { useTranslations } from 'next-intl';

export interface ChronologyEvent {
  date: string;
  type: string;
  desc: string;
  impact: string;
}

/** Claim chronology: incident, declaration, analyses and recorded decisions. */
export default function TimelineTab({ events }: { events: ChronologyEvent[] }) {
  const t = useTranslations('caseCockpit.timelineTab');
  return (
    <ol className="space-y-3 text-sm" aria-label={t('label')}>
      {events.map((event, index) => (
        <li key={index} className="flex items-start gap-4 rounded-lg border border-slate-100 p-3">
          <span className="w-20 flex-shrink-0 font-medium text-slate-500">{event.date}</span>
          <span
            className={clsx(
              'mt-1.5 h-2.5 w-2.5 flex-shrink-0 rounded-full',
              event.impact === 'supports' ? 'bg-emerald-500' : event.impact === 'disputes' ? 'bg-rose-500' : 'bg-slate-300',
            )}
            aria-hidden
          />
          <div className="min-w-0">
            <p className="font-medium text-slate-900">{event.type}</p>
            <p className="text-slate-600">{event.desc}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
