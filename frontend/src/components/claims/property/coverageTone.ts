import { CircleAlert, CircleCheck, CircleHelp, CircleMinus, CircleX, TriangleAlert, type LucideIcon } from 'lucide-react';
import type { CoverageTone } from './coverageView';

interface ToneStyle {
  Icon: LucideIcon;
  icon: string;
  chip: string;
  card: string;
  bar: string;
}

/** Icon and colours of a coverage status, shared by every section of the "Cover & amounts" tab. */
export const TONE_STYLE: Record<CoverageTone, ToneStyle> = {
  covered: {
    Icon: CircleCheck,
    icon: 'text-emerald-600',
    chip: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
    card: 'border-emerald-200 bg-emerald-50',
    bar: 'bg-emerald-500',
  },
  partial: {
    Icon: CircleAlert,
    icon: 'text-amber-600',
    chip: 'bg-amber-50 text-amber-800 ring-amber-200',
    card: 'border-amber-200 bg-amber-50',
    bar: 'bg-amber-400',
  },
  review: {
    Icon: TriangleAlert,
    icon: 'text-amber-600',
    chip: 'bg-amber-50 text-amber-800 ring-amber-200',
    card: 'border-amber-200 bg-amber-50',
    bar: 'bg-amber-400',
  },
  excluded: {
    Icon: CircleX,
    icon: 'text-rose-600',
    chip: 'bg-rose-50 text-rose-800 ring-rose-200',
    card: 'border-rose-200 bg-rose-50',
    bar: 'bg-rose-400',
  },
  notConcerned: {
    Icon: CircleMinus,
    icon: 'text-slate-400',
    chip: 'bg-slate-50 text-slate-600 ring-slate-200',
    card: 'border-slate-200 bg-slate-50',
    bar: 'bg-slate-300',
  },
  unknown: {
    Icon: CircleHelp,
    icon: 'text-slate-500',
    chip: 'bg-slate-50 text-slate-700 ring-slate-200',
    card: 'border-slate-200 bg-slate-50',
    bar: 'bg-slate-300',
  },
};
