'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Users,
  Settings,
  LogOut,
  User,
  Database,
  Loader2,
} from 'lucide-react';
import { listCustomers, seedCustomer360Data } from '@/lib/customer360-api';
import type { CustomerProfile } from '@/lib/customer360-types';
import CustomerListView from '@/components/customer360/CustomerListView';
import PersonaSelector from '@/components/PersonaSelector';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import CurrencySwitcher from '@/components/CurrencySwitcher';
import { useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';
import BrandMark from '@/components/BrandMark';
import AppearanceSwitcher from '@/components/AppearanceSwitcher';

export default function CustomersPage() {
  const [customers, setCustomers] = useState<CustomerProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const router = useRouter();
  const t = useTranslations('customer360');
  const [authUser, setAuthUser] = useState<string | null>(null);
  const [authEnabled, setAuthEnabled] = useState(false);

  useEffect(() => {
    fetchCustomers();
    checkAuth();
  }, []);

  async function fetchCustomers() {
    try {
      setLoading(true);
      const data = await listCustomers();
      setCustomers(data);
    } catch (err) {
      console.error('Failed to load customers:', err);
      setCustomers([]);
    } finally {
      setLoading(false);
    }
  }

  async function checkAuth() {
    try {
      const res = await fetch('/api/auth/check');
      const data = await res.json();
      if (data.authEnabled) {
        setAuthEnabled(true);
        setAuthUser(data.username || null);
      }
    } catch {
      // ignore
    }
  }

  async function handleSeedData() {
    try {
      setSeeding(true);
      await seedCustomer360Data();
      await fetchCustomers();
    } catch (err) {
      console.error('Failed to seed data:', err);
    } finally {
      setSeeding(false);
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
              <BrandMark compact />
            </Link>

            <PersonaSelector />

            {/* Active tab indicator */}
            <div
              className="flex items-center gap-1 px-3 py-1.5 border rounded-lg"
              style={{ backgroundColor: `${brand.primary}0D`, borderColor: `${brand.primary}33` }}
            >
              <Users className="w-4 h-4" style={{ color: brand.ink }} />
              <span className="text-sm font-medium" style={{ color: brand.ink }}>{t('title')}</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/admin"
              className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <Settings className="w-4 h-4" />
              <span>{t('admin')}</span>
            </Link>

            <LanguageSwitcher />
            <CurrencySwitcher />
            <AppearanceSwitcher />

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
                  style={{ color: brand.ink, backgroundColor: `${brand.primary}0D` }}
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
        {/* Page Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center"
                style={{ background: `linear-gradient(135deg, ${brand.gradientStart}, ${brand.gradientEnd})` }}
              >
                <Users className="w-5 h-5 text-white" />
              </div>
              {t('title')}
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              {t('subtitle')}
            </p>
          </div>

          {/* Seed data button (for demo) */}
          {!loading && customers.length === 0 && (
            <button
              onClick={handleSeedData}
              disabled={seeding}
              className="flex items-center gap-2 px-4 py-2 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
              style={{ backgroundColor: brand.primary }}
            >
              {seeding ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Database className="w-4 h-4" />
              )}
              {seeding ? t('seeding') : t('loadSampleData')}
            </button>
          )}
        </div>

        {/* Customer List */}
        <CustomerListView
          customers={customers}
          loading={loading}
          onSelectCustomer={(id) => router.push(`/customers/${id}`)}
        />
      </main>
    </div>
  );
}
