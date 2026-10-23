'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Check, Mail, RefreshCw, UserPlus, X } from 'lucide-react';
import clsx from 'clsx';
import { brand } from '@/lib/brand';

type AccessStatus = 'pending' | 'approved' | 'refused';

type AccessEntry = {
  id: string;
  email: string | null;
  name: string | null;
  status: AccessStatus;
  requested_at: string;
  decided_at: string | null;
  decided_by: string | null;
  notification_status?: 'not_requested' | 'sending' | 'submitted' | 'failed';
  notification_at?: string | null;
  approval_notification_status?: 'not_requested' | 'sending' | 'submitted' | 'failed';
  approval_notification_at?: string | null;
};

const STATUS_STYLE: Record<AccessStatus, string> = {
  pending: 'bg-amber-50 text-amber-700 border-amber-200',
  approved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  refused: 'bg-slate-100 text-slate-600 border-slate-200',
};

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Admin tab: Microsoft Entra ID access requests (approve / refuse / pre-authorize). */
export default function AccessRequestsTab() {
  const t = useTranslations('adminPanel.accessRequests');
  const tAdmin = useTranslations('adminPanel');
  const locale = useLocale();
  const [items, setItems] = useState<AccessEntry[] | null>(null);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError('');
    try {
      const res = await fetch('/api/auth/access-requests', { cache: 'no-store' });
      if (!res.ok) throw new Error(String(res.status));
      setItems(((await res.json()) as { items: AccessEntry[] }).items);
    } catch {
      setError(t('loadError'));
      setItems([]);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function post(key: string, url: string, body: object) {
    setBusy(key);
    setError('');
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(String(res.status));
      await load();
      return true;
    } catch {
      setError(t('actionError'));
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function authorize(e: FormEvent) {
    e.preventDefault();
    const value = email.trim().toLowerCase();
    if (!EMAIL_RE.test(value)) {
      setError(t('invalidEmail'));
      return;
    }
    if (await post('authorize', '/api/auth/access-requests', { email: value })) setEmail('');
  }

  const decide = (entry: AccessEntry, decision: 'approve' | 'refuse') =>
    post(entry.id, `/api/auth/access-requests/${encodeURIComponent(entry.id)}`, { decision });

  const formatDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' }) : '—';
  const pending = items?.filter((i) => i.status === 'pending').length ?? 0;

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-sm text-slate-600">{t('lead')}</p>
          <p className="mt-2 text-sm font-medium" style={{ color: brand.primary }}>
            {t('pendingCount', { count: pending })}
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          {tAdmin('refresh')}
        </button>
      </div>

      <form onSubmit={authorize} className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <label className="flex min-w-[280px] flex-1 flex-col gap-1.5 text-sm font-medium text-slate-700">
          {t('authorizeLabel')}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t('authorizePlaceholder')}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal focus:outline-none focus:ring-2"
          />
        </label>
        <button
          type="submit"
          disabled={busy === 'authorize' || !email.trim()}
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          style={{ backgroundColor: brand.primary }}
        >
          <UserPlus className="h-4 w-4" />
          {t('authorizeButton')}
        </button>
      </form>

      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {items === null ? (
        <p className="text-sm text-slate-500">{t('loading')}</p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          {t('empty')}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                {(['name', 'email', 'requested', 'status', 'notification', 'approvalNotification', 'decidedBy', 'actions'] as const).map((col) => (
                  <th key={col} className="px-4 py-3">{t(col)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((entry) => (
                <tr key={entry.id}>
                  <td className="px-4 py-3 text-slate-900">{entry.name || '—'}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{entry.email || entry.id}</td>
                  <td className="px-4 py-3 text-slate-600">{formatDate(entry.requested_at)}</td>
                  <td className="px-4 py-3">
                    <span className={clsx('rounded-full border px-2.5 py-0.5 text-xs font-medium', STATUS_STYLE[entry.status])}>
                      {t(entry.status)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    <span className={clsx(entry.notification_status === 'failed' && 'font-medium text-red-700')}>
                      {t(`notification_${entry.notification_status || 'not_requested'}`)}
                    </span>
                    {entry.notification_at && (
                      <span className="mt-1 block">{formatDate(entry.notification_at)}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    <span className={clsx(entry.approval_notification_status === 'failed' && 'font-medium text-red-700')}>
                      {t(`notification_${entry.approval_notification_status || 'not_requested'}`)}
                    </span>
                    {entry.approval_notification_at && (
                      <span className="mt-1 block">{formatDate(entry.approval_notification_at)}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {entry.decided_by ? `${entry.decided_by} · ${formatDate(entry.decided_at)}` : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      {entry.status !== 'approved' && (
                        <button
                          disabled={busy === entry.id}
                          onClick={() => void decide(entry, 'approve')}
                          className="flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                        >
                          <Check className="h-3.5 w-3.5" />
                          {t('approve')}
                        </button>
                      )}
                      {entry.status !== 'refused' && (
                        <button
                          disabled={busy === entry.id}
                          onClick={() => void decide(entry, 'refuse')}
                          className="flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                        >
                          <X className="h-3.5 w-3.5" />
                          {t(entry.status === 'approved' ? 'revoke' : 'refuse')}
                        </button>
                      )}
                      {entry.email && (
                        <a
                          href={`mailto:${entry.email}`}
                          className="flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                        >
                          <Mail className="h-3.5 w-3.5" />
                          {t('mailUser')}
                        </a>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
