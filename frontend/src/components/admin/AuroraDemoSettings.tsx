'use client';

import { useTranslations } from 'next-intl';
import { Save, TestTube2 } from 'lucide-react';
import type { AuroraDemoScenario } from '@/lib/api';

const SCENARIOS: AuroraDemoScenario[] = [
  'swiss-chocolate-storm', 'swiss-watch-storm', 'wine-cellar',
];

export default function AuroraDemoSettings({
  enabled, scenario, validatedAt, validatedBy, liveConfigured, disabled,
  onEnabledChange, onScenarioChange, onSave,
}: {
  enabled: boolean;
  scenario: AuroraDemoScenario;
  validatedAt: string | null;
  validatedBy: string | null;
  liveConfigured: boolean;
  disabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
  onScenarioChange: (scenario: AuroraDemoScenario) => void;
  onSave: () => void;
}) {
  const t = useTranslations('auroraDemo');
  return (
    <section className="rounded-xl border border-violet-200 bg-violet-50 p-5 text-violet-950">
      <h3 className="flex items-center gap-2 font-semibold">
        <TestTube2 className="h-5 w-5" aria-hidden />{t('title')}
      </h3>
      <p className="mt-1 text-xs">{t('shortNotice')}</p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
      <label className="flex items-center gap-2 text-sm font-medium">
        <input type="checkbox" checked={enabled} disabled={disabled}
          onChange={event => onEnabledChange(event.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-violet-300" />
        {t('confirm')}
      </label>
      <label className="grid gap-1.5 text-sm font-medium">
        {t('scenario')}
        <select aria-label={t('scenario')} value={scenario} disabled={disabled}
          onChange={event => {
            const selected = SCENARIOS.find(id => id === event.target.value);
            if (selected) onScenarioChange(selected);
          }}
          className="rounded-lg border border-violet-300 bg-white px-3 py-2 text-sm">
          {SCENARIOS.map(id => <option key={id} value={id}>{t(`scenarios.${id}`)}</option>)}
        </select>
      </label>
      </div>
      <p className="mt-2 text-xs">{t('scenarioScopeHelp')}</p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" onClick={onSave} disabled={disabled}
          className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-violet-950 px-3 py-2 text-xs font-semibold text-white hover:bg-violet-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-700 disabled:opacity-50">
          <Save className="h-4 w-4" aria-hidden />{t('saveMode')}
        </button>
        {validatedAt && validatedBy && (
          <p className="text-xs">{t('validated', { admin: validatedBy, at: validatedAt })}</p>
        )}
      </div>
      <details className="mt-3 text-xs">
        <summary className="cursor-pointer font-medium">{t('guideTitle')}</summary>
        <div className="mt-2 space-y-2">
          <p>{t('notice')}</p>
          <p>{t('presentation')}</p>
          <p>{t('saveHelp')}</p>
          <p>{t('guide')}</p>
          <p>{t(liveConfigured ? 'liveConfigured' : 'liveNotConfigured')}</p>
        </div>
      </details>
      <p className="mt-2 text-xs font-medium">{t('billing')}</p>
    </section>
  );
}
