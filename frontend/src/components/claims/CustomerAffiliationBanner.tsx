'use client';

import React, { useState, useCallback } from 'react';
import { UserPlus, Link2, X, Check, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface CustomerAffiliationBannerProps {
  applicationId: string;
  /** Pre-filled fields from extraction */
  suggestedName?: string;
  suggestedAddress?: string;
  suggestedPhone?: string;
  suggestedEmail?: string;
  /** Called when affiliation succeeds — parent should refresh */
  onAffiliated?: (customerId: string) => void;
}

export default function CustomerAffiliationBanner({
  applicationId,
  suggestedName = '',
  suggestedAddress = '',
  suggestedPhone = '',
  suggestedEmail = '',
  onAffiliated,
}: CustomerAffiliationBannerProps) {
  const t = useTranslations('customerAffiliation');
  const [mode, setMode] = useState<'banner' | 'create' | 'link'>('banner');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  // Create form state
  const [name, setName] = useState(suggestedName);
  const [address, setAddress] = useState(suggestedAddress);
  const [phone, setPhone] = useState(suggestedPhone);
  const [email, setEmail] = useState(suggestedEmail);

  // Link form state
  const [customers, setCustomers] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const loadCustomers = useCallback(async () => {
    try {
      const res = await fetch('/api/customers');
      if (res.ok) {
        const data = await res.json();
        setCustomers(data);
      }
    } catch { /* ignore */ }
  }, []);

  const handleCreate = useCallback(async () => {
    if (!name.trim()) { setError(t('nameRequired')); return; }
    setLoading(true);
    setError(null);
    try {
      // Step 1: Create customer
      const createRes = await fetch('/api/customers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), address, phone, email }),
      });
      if (!createRes.ok) {
        const err = await createRes.json().catch(() => ({ detail: t('createError') }));
        throw new Error(err.detail || t('createError'));
      }
      const customer = await createRes.json();

      // Step 2: Affiliate application
      const affRes = await fetch(`/api/applications/${applicationId}/affiliate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: customer.id }),
      });
      if (!affRes.ok) {
        const err = await affRes.json().catch(() => ({ detail: t('affiliateError') }));
        throw new Error(err.detail || t('affiliateError'));
      }

      setSuccess(t('createdAndAffiliated', { name: customer.name, id: customer.id }));
      onAffiliated?.(customer.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('genericError'));
    } finally {
      setLoading(false);
    }
  }, [name, address, phone, email, applicationId, onAffiliated, t]);

  const handleLink = useCallback(async () => {
    if (!selectedCustomerId) { setError(t('selectCustomer')); return; }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/applications/${applicationId}/affiliate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: selectedCustomerId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: t('affiliateError') }));
        throw new Error(err.detail || t('affiliateError'));
      }
      const data = await res.json();
      setSuccess(data.message || t('fileAffiliated'));
      onAffiliated?.(selectedCustomerId);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('genericError'));
    } finally {
      setLoading(false);
    }
  }, [selectedCustomerId, applicationId, onAffiliated, t]);

  if (dismissed || success) {
    if (success) {
      return (
        <div className="mx-4 mt-2 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2 flex items-center gap-3">
          <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <p className="text-sm text-emerald-700">{success}</p>
          <button onClick={() => setDismissed(true)} className="ml-auto text-emerald-600 hover:text-emerald-800"><X className="w-4 h-4" /></button>
        </div>
      );
    }
    return null;
  }

  // Banner mode
  if (mode === 'banner') {
    return (
      <div className="mx-4 mt-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 flex items-center gap-3">
        <UserPlus className="w-4 h-4 text-amber-600 flex-shrink-0" />
        <p className="text-sm text-amber-800">{t('bannerMessage')}</p>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => { setMode('create'); setName(suggestedName); setAddress(suggestedAddress); setPhone(suggestedPhone); setEmail(suggestedEmail); }}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors"
          >
            <UserPlus className="w-3 h-3" />
            {t('createCustomer')}
          </button>
          <button
            onClick={() => { setMode('link'); loadCustomers(); }}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-indigo-600 bg-white border border-indigo-200 rounded-lg hover:bg-indigo-50 transition-colors"
          >
            <Link2 className="w-3 h-3" />
            {t('linkExisting')}
          </button>
          <button onClick={() => setDismissed(true)} className="p-1 text-amber-500 hover:text-amber-700">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  // Create mode
  if (mode === 'create') {
    return (
      <div className="mx-4 mt-2 bg-white border border-indigo-200 rounded-lg p-4 shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <UserPlus className="w-4 h-4 text-indigo-600" />
          <h3 className="text-sm font-semibold text-slate-900">{t('createTitle')}</h3>
          <button onClick={() => setMode('banner')} className="ml-auto p-1 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
        </div>
        {error && <p className="text-xs text-rose-600 mb-2">{error}</p>}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="block text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">{t('fieldName')}</label>
            <input type="text" value={name} onChange={e => setName(e.target.value)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('namePlaceholder')} />
          </div>
          <div>
            <label className="block text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">{t('fieldEmail')}</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('emailPlaceholder')} />
          </div>
          <div>
            <label className="block text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">{t('fieldAddress')}</label>
            <input type="text" value={address} onChange={e => setAddress(e.target.value)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('addressPlaceholder')} />
          </div>
          <div>
            <label className="block text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">{t('fieldPhone')}</label>
            <input type="tel" value={phone} onChange={e => setPhone(e.target.value)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('phonePlaceholder')} />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={() => setMode('banner')} className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800">{t('cancel')}</button>
          <button onClick={handleCreate} disabled={loading}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
            {t('createAndAffiliate')}
          </button>
        </div>
      </div>
    );
  }

  // Link mode
  const filteredCustomers = searchQuery
    ? customers.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()) || c.id.toLowerCase().includes(searchQuery.toLowerCase()))
    : customers;

  return (
    <div className="mx-4 mt-2 bg-white border border-indigo-200 rounded-lg p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <Link2 className="w-4 h-4 text-indigo-600" />
        <h3 className="text-sm font-semibold text-slate-900">{t('linkTitle')}</h3>
        <button onClick={() => setMode('banner')} className="ml-auto p-1 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
      </div>
      {error && <p className="text-xs text-rose-600 mb-2">{error}</p>}
      <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
        placeholder={t('searchPlaceholder')}
        className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-2" />
      <div className="max-h-40 overflow-y-auto border border-slate-200 rounded-lg mb-3">
        {filteredCustomers.length === 0 ? (
          <p className="text-xs text-slate-500 italic p-3 text-center">{t('noCustomersFound')}</p>
        ) : filteredCustomers.map(c => (
          <button key={c.id} onClick={() => setSelectedCustomerId(c.id)}
            className={`w-full text-left px-3 py-2 text-sm border-b border-slate-100 last:border-0 transition-colors ${selectedCustomerId === c.id ? 'bg-indigo-50 text-indigo-700' : 'hover:bg-slate-50 text-slate-700'}`}>
            <span className="font-medium">{c.name}</span>
            <span className="text-[10px] text-slate-400 ml-2">{c.id}</span>
          </button>
        ))}
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={() => setMode('banner')} className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800">{t('cancel')}</button>
        <button onClick={handleLink} disabled={loading || !selectedCustomerId}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Link2 className="w-3 h-3" />}
          {t('affiliate')}
        </button>
      </div>
    </div>
  );
}
