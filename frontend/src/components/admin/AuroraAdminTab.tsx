'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  Check,
  CircleAlert,
  CloudSun,
  Database,
  LoaderCircle,
  PhoneCall,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  TestTube2,
  TriangleAlert,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';
import AuroraExpiryCountdown from '@/components/aurora/AuroraExpiryCountdown';

type AuroraConfig = {
  enabled: boolean;
  endpoint: string;
  deterministic_model: string;
  ensemble_model: string;
  initial_condition_blob_url: string;
  channel_container_url: string;
  default_horizon_hours: number;
  endpoint_expires_at: string | null;
  updated_at: string | null;
  updated_by: string | null;
};

type AuroraSnapshot = {
  configuration: AuroraConfig;
  source: 'admin' | 'environment';
  runtime: {
    enabled: boolean;
    configured: boolean;
    model: string;
    missing: string[];
  };
  checklist: Array<{ id: string; ready: boolean }>;
  ready_count: number;
  total_count: number;
  input_contract: {
    history_steps: number;
    surface_variables: number;
    atmospheric_variables: number;
    format: string;
    cadence: string;
  };
  security: {
    endpoint_authentication: 'managed_identity' | 'key_vault_secret';
    storage_authentication: 'managed_identity';
    secrets_persisted: boolean;
    sas_persisted: boolean;
  };
};

type TestResult = {
  ok: boolean;
  checks: Array<{ id: string; ok: boolean; detail: string }>;
};

const EMPTY_CONFIG: AuroraConfig = {
  enabled: false,
  endpoint: '',
  deterministic_model: 'aurora-0.25-v1.5',
  ensemble_model: 'aurora-0.25-v1.5-ensemble',
  initial_condition_blob_url: '',
  channel_container_url: '',
  default_horizon_hours: 12,
  endpoint_expires_at: null,
  updated_at: null,
  updated_by: null,
};

async function responseError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({})) as { detail?: string; error?: string };
  return body.detail || body.error || fallback;
}

function toLocalDateTime(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 19);
}

export default function AuroraAdminTab() {
  const t = useTranslations('adminPanel.aurora');
  const [snapshot, setSnapshot] = useState<AuroraSnapshot | null>(null);
  const [form, setForm] = useState<AuroraConfig>(EMPTY_CONFIG);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch('/api/admin/aurora', { cache: 'no-store' });
      if (!response.ok) throw new Error(await responseError(response, t('loadError')));
      const value = await response.json() as AuroraSnapshot;
      setSnapshot(value);
      setForm(value.configuration);
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof Error ? error.message : t('loadError') });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    let active = true;
    fetch('/api/admin/aurora', { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response, t('loadError')));
        return response.json() as Promise<AuroraSnapshot>;
      })
      .then((value) => {
        if (!active) return;
        setSnapshot(value);
        setForm(value.configuration);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setMessage({ kind: 'error', text: error instanceof Error ? error.message : t('loadError') });
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [t]);

  async function save() {
    setSaving(true);
    setMessage(null);
    setTestResult(null);
    try {
      const response = await fetch('/api/admin/aurora', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!response.ok) throw new Error(await responseError(response, t('saveError')));
      const value = await response.json() as AuroraSnapshot;
      setSnapshot(value);
      setForm(value.configuration);
      setMessage({ kind: 'success', text: t('saved') });
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof Error ? error.message : t('saveError') });
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    setTesting(true);
    setMessage(null);
    try {
      const response = await fetch('/api/admin/aurora/test', { method: 'POST' });
      if (!response.ok) throw new Error(await responseError(response, t('testError')));
      const value = await response.json() as TestResult;
      setTestResult(value);
      setMessage({ kind: value.ok ? 'success' : 'error', text: value.ok ? t('testPassed') : t('testFailed') });
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof Error ? error.message : t('testError') });
    } finally {
      setTesting(false);
    }
  }

  const readinessPercent = snapshot
    ? Math.round((snapshot.ready_count / snapshot.total_count) * 100)
    : 0;
  const agentContext = useMemo(() => JSON.stringify({
    source: 'aurora-0.25-v1.5',
    location: { latitude: 46.2, longitude: 6.1 },
    horizon_hours: form.default_horizon_hours,
    weather_evidence: {
      max_wind_gust_ms: 27.4,
      total_precipitation_mm: 36.2,
      hazard_window: { starts_at: '…', ends_at: '…' },
    },
    decision_support: {
      severity: 'high',
      triage_priority: 'priority',
      recommended_actions: ['contact_customer', 'preserve_evidence', 'expedite_adjuster'],
      human_review_required: true,
    },
    provenance: { provider: 'Microsoft Foundry', generated_at: '…' },
  }, null, 2), [form.default_horizon_hours]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white p-12 text-sm text-slate-600">
        <LoaderCircle className="h-5 w-5 animate-spin" aria-hidden />
        {t('loading')}
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-950 text-white shadow-sm">
        <div className="grid gap-6 p-6 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-teal-300">
              <CloudSun className="h-5 w-5" aria-hidden />
              {t('eyebrow')}
            </div>
            <h2 className="mt-3 text-2xl font-semibold">{t('title')}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{t('lead')}</p>
            <div className="mt-5 flex flex-wrap gap-2 text-xs">
              {(['hourly', 'variables', 'ensemble', 'advisory'] as const).map((key) => (
                <span key={key} className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5">
                  {t(`facts.${key}`)}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{t('readiness')}</span>
              <span className="text-2xl font-semibold text-teal-300">{readinessPercent}%</span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-teal-400 transition-all" style={{ width: `${readinessPercent}%` }} />
            </div>
            <p className="mt-3 text-xs text-slate-300">
              {t('readyCount', { ready: snapshot?.ready_count ?? 0, total: snapshot?.total_count ?? 5 })}
            </p>
            <p className="mt-1 text-xs text-slate-400">{t(`source.${snapshot?.source ?? 'environment'}`)}</p>
          </div>
        </div>
      </div>

      <AuroraExpiryCountdown expiresAt={form.endpoint_expires_at} />

      {message && (
        <p
          role="alert"
          className={clsx(
            'rounded-xl border px-4 py-3 text-sm',
            message.kind === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-red-200 bg-red-50 text-red-800',
          )}
        >
          {message.text}
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.45fr_1fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
                <ShieldCheck className="h-5 w-5 text-teal-600" aria-hidden />
                {t('configuration.title')}
              </h3>
              <p className="mt-1 text-sm text-slate-600">{t('configuration.lead')}</p>
            </div>
            <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
                className="h-4 w-4 rounded border-slate-300"
              />
              {t('configuration.enabled')}
            </label>
          </div>

          <div className="mt-6 grid gap-4">
            {([
              ['endpoint', 'url'],
              ['initial_condition_blob_url', 'url'],
              ['channel_container_url', 'url'],
              ['deterministic_model', 'text'],
              ['ensemble_model', 'text'],
            ] as const).map(([field, type]) => (
              <label key={field} className="grid gap-1.5 text-sm font-medium text-slate-700">
                {t(`configuration.fields.${field}.label`)}
                <input
                  type={type}
                  value={form[field]}
                  onChange={(event) => setForm({ ...form, [field]: event.target.value })}
                  placeholder={t(`configuration.fields.${field}.placeholder`)}
                  className="rounded-lg border border-slate-300 px-3 py-2.5 font-mono text-xs font-normal text-slate-900 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100"
                />
                <span className="text-xs font-normal text-slate-500">{t(`configuration.fields.${field}.help`)}</span>
              </label>
            ))}
            <label className="grid gap-1.5 text-sm font-medium text-slate-700">
              {t('configuration.fields.default_horizon_hours.label')}
              <select
                value={form.default_horizon_hours}
                onChange={(event) => setForm({ ...form, default_horizon_hours: Number(event.target.value) })}
                className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm font-normal text-slate-900"
              >
                {[6, 12, 24, 48, 72].map((hours) => (
                  <option key={hours} value={hours}>{t('hours', { count: hours })}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-slate-700">
              {t('configuration.fields.endpoint_expires_at.label')}
              <input
                type="datetime-local"
                step="1"
                value={toLocalDateTime(form.endpoint_expires_at)}
                onChange={(event) => setForm({
                  ...form,
                  endpoint_expires_at: event.target.value
                    ? new Date(event.target.value).toISOString()
                    : null,
                })}
                className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm font-normal text-slate-900"
              />
              <span className="text-xs font-normal text-slate-500">
                {t('configuration.fields.endpoint_expires_at.help')}
              </span>
            </label>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
              style={{ backgroundColor: brand.primary }}
            >
              {saving ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Save className="h-4 w-4" aria-hidden />}
              {saving ? t('saving') : t('save')}
            </button>
            <button
              type="button"
              onClick={() => void testConnection()}
              disabled={testing || !snapshot?.runtime.enabled}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {testing ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <TestTube2 className="h-4 w-4" aria-hidden />}
              {testing ? t('testing') : t('test')}
            </button>
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm text-slate-500 hover:bg-slate-50"
            >
              <RefreshCw className="h-4 w-4" aria-hidden />
              {t('reload')}
            </button>
          </div>
          <p className="mt-3 text-xs text-slate-500">{t('configuration.security')}</p>
        </div>

        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-base font-semibold text-slate-900">{t('checklist.title')}</h3>
            <div className="mt-4 space-y-3">
              {snapshot?.checklist.map((item) => {
                const tested = testResult?.checks.find((check) => check.id === item.id);
                const ready = tested ? tested.ok : item.ready;
                return (
                  <div key={item.id} className="flex items-start gap-3">
                    <span className={clsx(
                      'mt-0.5 flex h-5 w-5 items-center justify-center rounded-full',
                      ready ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400',
                    )}>
                      {ready ? <Check className="h-3.5 w-3.5" aria-hidden /> : <X className="h-3.5 w-3.5" aria-hidden />}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-slate-800">{t(`checklist.items.${item.id}`)}</p>
                      {tested && <p className="text-xs text-slate-500">{t(tested.ok ? 'checklist.testPassed' : 'checklist.testFailed')}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-2xl border border-blue-200 bg-blue-50 p-5">
            <h3 className="flex items-center gap-2 font-semibold text-blue-950">
              <Database className="h-5 w-5" aria-hidden />
              {t('inputContract.title')}
            </h3>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              {([
                ['history', snapshot?.input_contract.history_steps],
                ['surface', snapshot?.input_contract.surface_variables],
                ['atmospheric', snapshot?.input_contract.atmospheric_variables],
                ['format', snapshot?.input_contract.format],
              ] as const).map(([key, value]) => (
                <div key={key} className="rounded-lg bg-white/70 p-3">
                  <dt className="text-xs text-blue-700">{t(`inputContract.${key}`)}</dt>
                  <dd className="mt-1 font-semibold text-blue-950">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
            <Sparkles className="h-5 w-5 text-violet-600" aria-hidden />
            {t('agentContext.title')}
          </h3>
          <p className="mt-1 text-sm text-slate-600">{t('agentContext.lead')}</p>
          <pre className="mt-4 max-h-[28rem] overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-5 text-teal-200">
            {agentContext}
          </pre>
          <p className="mt-3 flex items-start gap-2 text-xs text-slate-500">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            {t('agentContext.guardrail')}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
            <BarChart3 className="h-5 w-5 text-teal-600" aria-hidden />
            {t('roi.title')}
          </h3>
          <p className="mt-1 text-sm text-slate-600">{t('roi.lead')}</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {([
              ['triage', TriangleAlert],
              ['outreach', PhoneCall],
              ['evidence', ShieldCheck],
              ['portfolio', BarChart3],
            ] as const).map(([key, Icon]) => (
              <div key={key} className="rounded-xl border border-slate-200 p-4">
                <Icon className="h-5 w-5 text-teal-600" aria-hidden />
                <p className="mt-3 text-sm font-semibold text-slate-900">{t(`roi.items.${key}.title`)}</p>
                <p className="mt-1 text-xs leading-5 text-slate-600">{t(`roi.items.${key}.body`)}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-5 text-amber-900">
            {t('roi.measurement')}
          </div>
        </div>
      </div>
    </section>
  );
}
