'use client';

import { useLocale, useTranslations } from 'next-intl';
import clsx from 'clsx';
import { isNewSince, type CaseUpdate } from './caseUpdates';
import { CockpitCard } from './caseUi';

interface LatestUpdatesProps {
  updates: CaseUpdate[];
  previousVisit: number | null;
  onOpenTimeline: () => void;
  limit?: number;
}

const LEVELS = new Set(['calm', 'moderate', 'stressed', 'critical']);
const BANDS = new Set(['LOW', 'MODERATE', 'HIGH']);
const DECISIONS = new Set(['approve', 'approve_with_conditions', 'defer', 'decline']);
const WEB_VERDICTS = new Set(['confirmed', 'notConfirmed', 'unclear', 'skipped']);

/** What happened on the case lately, with a "new" badge since the previous visit. */
export default function LatestUpdates({ updates, previousVisit, onOpenTimeline, limit = 4 }: LatestUpdatesProps) {
  const t = useTranslations('caseCockpit');
  const tDecisions = useTranslations('decisions');
  const locale = useLocale();
  const format = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

  const describe = (update: CaseUpdate): string => {
    const { params } = update;
    switch (update.kind) {
      case 'created':
        return t('updates.kinds.created', { files: params.files });
      case 'extraction':
        return t('updates.kinds.extraction', { files: params.files, fields: params.fields });
      case 'analysis':
        return params.review ? t('updates.kinds.analysisReview') : t('updates.kinds.analysis');
      case 'sentiment': {
        const level = String(params.level);
        return t('updates.kinds.sentiment', {
          level: LEVELS.has(level) ? t(`kpi.customerLevels.${level}`) : level,
          score: params.score,
        });
      }
      case 'fraud': {
        const band = String(params.band);
        const values = { band: BANDS.has(band) ? t(`updates.bands.${band}`) : band, score: params.score };
        return params.siu ? t('updates.kinds.fraudSiu', values) : t('updates.kinds.fraud', values);
      }
      case 'webCheck': {
        const verdict = String(params.verdict);
        return t(`updates.kinds.web.${WEB_VERDICTS.has(verdict) ? verdict : 'unclear'}`, { sources: params.sources });
      }
      case 'decision': {
        const decision = String(params.decision);
        return t('updates.kinds.decision', { decision: DECISIONS.has(decision) ? tDecisions(decision) : decision });
      }
      default:
        return update.label || '—';
    }
  };

  const visible = updates.slice(0, limit);

  return (
    <CockpitCard
      title={t('updates.title')}
      headingId="cockpit-updates"
      aside={
        <button type="button" onClick={onOpenTimeline} className="text-sm font-medium text-indigo-700 hover:underline">
          {t('updates.full')}
        </button>
      }
    >
      {visible.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate-500">{t('updates.none')}</p>
      ) : (
        <ol className="space-y-3 px-4 py-3 text-sm">
          {visible.map((update) => {
            const fresh = isNewSince(update, previousVisit);
            return (
              <li key={update.id} className="flex gap-3">
                <span
                  className={clsx('mt-1.5 h-2 w-2 flex-shrink-0 rounded-full', fresh ? 'bg-indigo-600' : 'bg-slate-300')}
                  aria-hidden
                />
                <div className="min-w-0">
                  <p className="text-slate-800">
                    {describe(update)}
                    {fresh && (
                      <span className="ml-1.5 rounded bg-indigo-600 px-1.5 py-0.5 text-xs font-semibold text-white">
                        {t('updates.new')}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500">
                    <time dateTime={new Date(update.at).toISOString()}>{format.format(update.at)}</time>
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </CockpitCard>
  );
}
