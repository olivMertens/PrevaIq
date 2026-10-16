'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Users,
  Settings,
  LogOut,
  User,
  Loader2,
} from 'lucide-react';
import { getCustomer360 } from '@/lib/customer360-api';
import type { Customer360View } from '@/lib/customer360-types';
import CustomerProfileHeader from '@/components/customer360/CustomerProfileHeader';
import CustomerTimeline from '@/components/customer360/CustomerTimeline';
import PersonaSummaryCard from '@/components/customer360/PersonaSummaryCard';
import RiskCorrelationBanner from '@/components/customer360/RiskCorrelationBanner';
import SouscriaAcquisitionCard from '@/components/customer360/SouscriaAcquisitionCard';
import CustomerJourneyMetrics from '@/components/customer360/CustomerJourneyMetrics';
import PersonaSelector from '@/components/PersonaSelector';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';

export default function CustomerDetailPage() {
  const params = useParams();
  const router = useRouter();
  const customerId = params.id as string;
  const [data, setData] = useState<Customer360View | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const t = useTranslations('customer360');
  const tNav = useTranslations('nav');
  const [authUser, setAuthUser] = useState<string | null>(null);
  const [authEnabled, setAuthEnabled] = useState(false);

  useEffect(() => {
    if (customerId) {
      fetchCustomerData();
      checkAuth();
    }
  }, [customerId]);

  async function fetchCustomerData() {
    try {
      setLoading(true);
      setError(null);
      const result = await getCustomer360(customerId);
      setData(result);
    } catch (err) {
      console.error('Failed to load customer data:', err);
      setError('Customer not found');
    } finally {
      setLoading(false);
    }
  }

  async function checkAuth() {
    try {
      const res = await fetch('/api/auth/check');
      const d = await res.json();
      if (d.authEnabled) {
        setAuthEnabled(true);
        setAuthUser(d.username || null);
      }
    } catch {
      // ignore
    }
  }

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50/30">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2.5">
              <img
                src={brand.logo}
                alt={brand.logoAlt}
                className="h-9 w-auto"
              />
              <span className="text-slate-300 font-light select-none">|</span>
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="flex-shrink-0">
                <rect width="32" height="32" rx="8" fill="url(#giq-grad-cd)"/>
                <text x="16" y="22" textAnchor="middle" fontFamily="system-ui, sans-serif" fontWeight="800" fontSize="16" fill="white">IQ</text>
                <circle cx="26" cy="6" r="3" fill={brand.dotColor} opacity="0.9"/>
                <defs><linearGradient id="giq-grad-cd" x1="0" y1="0" x2="32" y2="32"><stop offset="0%" stopColor={brand.gradientStart}/><stop offset="100%" stopColor={brand.gradientEnd}/></linearGradient></defs>
              </svg>
              <span className="font-bold text-lg tracking-tight">
                <span className="text-slate-900">{brand.prefix}</span><span style={{ color: brand.primary }}>IQ</span>
              </span>
            </Link>

            <PersonaSelector />

            <Link
              href="/customers"
              className="flex items-center gap-1 px-3 py-1.5 border rounded-lg transition-colors"
              style={{ backgroundColor: `${brand.primary}0D`, borderColor: `${brand.primary}33` }}
            >
              <Users className="w-4 h-4" style={{ color: brand.primary }} />
              <span className="text-sm font-medium" style={{ color: brand.primary }}>{t('title')}</span>
            </Link>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/admin"
              className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <Settings className="w-4 h-4" />
              <span>{tNav('admin')}</span>
            </Link>

            <LanguageSwitcher />

            {authEnabled && (
              <div className="flex items-center gap-2 ml-2 pl-2 border-l border-slate-200">
                {authUser && (
                  <span className="flex items-center gap-1.5 text-sm text-slate-500">
                    <User className="w-3.5 h-3.5" />
                    {authUser}
                  </span>
                )}
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 text-sm text-slate-500 rounded-lg transition-colors"
                  style={{ color: brand.primary, backgroundColor: `${brand.primary}0D` }}
                  title={t('signOut')}
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl 2xl:max-w-[96rem] mx-auto px-6 py-8">
        {/* Back navigation */}
        <button
          onClick={() => router.push('/customers')}
          className="flex items-center gap-1.5 text-sm transition-colors mb-6"
          style={{ color: brand.primary }}
        >
          <ArrowLeft className="w-4 h-4" />
          {t('backToList')}
        </button>

        {loading && (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-8 h-8 animate-spin" style={{ color: brand.primary }} />
            <span className="ml-3 text-slate-500">{t('loadingCustomer')}</span>
          </div>
        )}

        {error && (
          <div className="text-center py-24">
            <Users className="w-12 h-12 mx-auto mb-3 text-slate-300" />
            <p className="text-lg font-medium text-slate-600">{error}</p>
            <button
              onClick={() => router.push('/customers')}
              className="mt-4 text-sm"
              style={{ color: brand.primary }}
            >
              ← {t('backToList')}
            </button>
          </div>
        )}

        {data && (
          <div className="space-y-6">
            {/* Profile Header */}
            <CustomerProfileHeader data={data} />

            {/* KPI Metrics Strip */}
            <CustomerJourneyMetrics data={data} />

            {/* Risk Correlations */}
            {data.risk_correlations.length > 0 && (
              <RiskCorrelationBanner correlations={data.risk_correlations} />
            )}

            {/* Two-column: Persona Summaries + Timeline */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Persona Summary Cards */}
              <div className="lg:col-span-1 space-y-4">
                {data.souscria_acquisition?.available && (
                  <SouscriaAcquisitionCard data={data.souscria_acquisition} />
                )}
                <h2 className="text-lg font-semibold text-slate-900">{t('productSummary')}</h2>
                {data.persona_summaries.map(summary => (
                  <PersonaSummaryCard key={summary.persona} summary={summary} />
                ))}
              </div>

              {/* Timeline */}
              <div className="lg:col-span-2">
                <CustomerTimeline events={data.journey_events} />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
