'use client';

import { CircleCheck, CircleHelp, OctagonAlert } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import { CockpitCard } from './caseUi';

export interface EvidencePhoto {
  filename: string;
  url: string;
  /** Authenticity score 0..1 from the fraud analysis, when checked. */
  score?: number;
  authentic?: boolean;
  galleryIndex: number;
}

interface EvidenceStripProps {
  photos: EvidencePhoto[];
  documentCount: number;
  onOpenPhoto: (galleryIndex: number) => void;
  onOpenAll: () => void;
}

const MAX_VISIBLE = 5;

function Badge({ photo }: { photo: EvidencePhoto }) {
  const t = useTranslations('caseCockpit.evidence');
  if (photo.score === undefined) return null;
  const score = Math.round(photo.score * 100);
  const variant = photo.authentic === false ? 'suspicious' : score < 75 ? 'doubtful' : 'authentic';
  const style = {
    authentic: { Icon: CircleCheck, className: 'text-emerald-800' },
    doubtful: { Icon: CircleHelp, className: 'text-amber-800' },
    suspicious: { Icon: OctagonAlert, className: 'text-rose-700' },
  }[variant];
  return (
    <span className={clsx('absolute bottom-1 left-1 inline-flex items-center gap-1 rounded bg-white/95 px-1.5 py-0.5 text-xs font-semibold', style.className)}>
      <style.Icon className="h-3.5 w-3.5" aria-hidden />
      {t(`badge.${variant}`, { score })}
    </span>
  );
}

/** Photos with their authenticity verdict at a glance; every document one click away. */
export default function EvidenceStrip({ photos, documentCount, onOpenPhoto, onOpenAll }: EvidenceStripProps) {
  const t = useTranslations('caseCockpit.evidence');
  const visible = photos.slice(0, MAX_VISIBLE);
  const extra = photos.length - visible.length;

  return (
    <CockpitCard
      title={t('title')}
      headingId="cockpit-evidence"
      aside={
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-600">{t('counts', { documents: documentCount, photos: photos.length })}</span>
          <button type="button" onClick={onOpenAll} className="font-medium text-indigo-700 hover:underline">{t('all')}</button>
        </div>
      }
    >
      {photos.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate-500">{t('noPhotos')}</p>
      ) : (
        <ul className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-5">
          {visible.map((photo, index) => {
            const isLast = index === visible.length - 1 && extra > 0;
            return (
              <li key={photo.filename}>
                <button
                  type="button"
                  onClick={() => (isLast ? onOpenAll() : onOpenPhoto(photo.galleryIndex))}
                  aria-label={isLast ? t('more', { count: extra }) : t('open', { name: photo.filename })}
                  className={clsx(
                    'relative block h-28 w-full overflow-hidden rounded-lg bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500',
                    photo.authentic === false && 'ring-2 ring-rose-500',
                  )}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- authenticated proxy URL, not a static asset */}
                  <img src={photo.url} alt={photo.filename} loading="lazy" decoding="async" className="h-full w-full object-cover" />
                  {isLast ? (
                    <span className="absolute inset-0 flex items-center justify-center bg-slate-900/60 text-lg font-semibold text-white">
                      +{extra}
                    </span>
                  ) : (
                    <Badge photo={photo} />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </CockpitCard>
  );
}
