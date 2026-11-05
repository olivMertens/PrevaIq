'use client';

import clsx from 'clsx';
import { BadgeCheck, Fingerprint, ShieldQuestion, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ImageProvenance } from '@/lib/api';

export type ProvenanceKind = 'aiGenerated' | 'credentials' | 'none' | 'unavailable';

/** Message that applies to a photo's Content Credentials (never a fraud verdict). */
export function provenanceKind(provenance: ImageProvenance): ProvenanceKind {
  if (provenance.status === 'c2pa') return provenance.ai_generated ? 'aiGenerated' : 'credentials';
  return provenance.status === 'none' ? 'none' : 'unavailable';
}

/** Generator and signer named by the manifest, e.g. "Microsoft AI ImageGen · Microsoft Corporation". */
export function provenanceDetails(provenance: ImageProvenance): string {
  return [provenance.generator, provenance.issuer].filter(Boolean).join(' · ');
}

const STYLES: Record<ProvenanceKind, string> = {
  aiGenerated: 'border-violet-200 bg-violet-50 text-violet-700',
  credentials: 'border-sky-200 bg-sky-50 text-sky-700',
  none: 'border-slate-200 bg-white text-slate-500',
  unavailable: 'border-slate-200 bg-white text-slate-400',
};

const ICONS = { aiGenerated: Sparkles, credentials: BadgeCheck, none: Fingerprint, unavailable: ShieldQuestion };

/** Content Credentials (C2PA) of a photo, shown next to its authenticity analysis. */
export default function ProvenanceBadge({ provenance, size = 'sm' }: { provenance?: ImageProvenance; size?: 'sm' | 'md' }) {
  const t = useTranslations('fraudAnalysis.provenance');
  if (!provenance) return null;
  const kind = provenanceKind(provenance);
  const Icon = ICONS[kind];
  const details = provenanceDetails(provenance);
  const tooltip = [
    t(`tooltip.${kind}`, { details: details || '—' }),
    provenance.used_in_score ? t('usedInScore') : t('informationOnly'),
  ].join(' ');
  return (
    <span
      title={tooltip}
      className={clsx(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5',
        size === 'md' ? 'text-sm' : 'text-xs',
        STYLES[kind],
      )}
    >
      <Icon className={size === 'md' ? 'h-4 w-4' : 'h-3 w-3'} aria-hidden />
      {t(`label.${kind}`)}
    </span>
  );
}
