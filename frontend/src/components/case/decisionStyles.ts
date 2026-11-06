import type { ApplicationDecision } from '@/lib/api';

export const DECISION_STYLES: Record<ApplicationDecision, { surface: string; button: string }> = {
  approve: { surface: 'border-emerald-500 bg-emerald-50 text-emerald-900', button: 'bg-emerald-700 hover:bg-emerald-800' },
  approve_with_conditions: { surface: 'border-amber-500 bg-amber-50 text-amber-950', button: 'bg-amber-700 hover:bg-amber-800' },
  defer: { surface: 'border-slate-400 bg-slate-100 text-slate-900', button: 'bg-slate-700 hover:bg-slate-800' },
  decline: { surface: 'border-rose-500 bg-rose-50 text-rose-900', button: 'bg-rose-700 hover:bg-rose-800' },
};
