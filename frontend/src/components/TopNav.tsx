'use client';

import Link from 'next/link';
import {
  LayoutDashboard,
  Clock,
  FileText,
  FileStack,
  Settings,
  ChevronDown,
  LogOut,
  User,
  Users,
} from 'lucide-react';
import type { ApplicationListItem, ApplicationMetadata } from '@/lib/types';
import clsx from 'clsx';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import PersonaSelector from './PersonaSelector';
import GlossaryDropdown from './GlossaryDropdown';
import { brand } from '@/lib/brand';
import { usePersona } from '@/lib/PersonaContext';
import { useTranslations } from 'next-intl';
import LanguageSwitcher from './LanguageSwitcher';
import DemoGuideModal from './DemoGuideModal';
import BrandMark from './BrandMark';
import StatusBadge from './landing/StatusBadge';
import { getApplicationDisplayTitle } from '@/lib/applicationDisplay';

interface TopNavProps {
  applications: ApplicationListItem[];
  selectedAppId?: string;
  selectedApp?: ApplicationMetadata;
  activeView: 'overview' | 'timeline' | 'documents' | 'source';
  onSelectApp: (appId: string) => void;
  onChangeView: (view: 'overview' | 'timeline' | 'documents' | 'source') => void;
  showWorkbenchControls?: boolean; // Show application selector and glossary (only in workbench view)
}

export default function TopNav({
  applications,
  selectedAppId,
  selectedApp,
  activeView,
  onSelectApp,
  onChangeView,
  showWorkbenchControls = false,
}: TopNavProps) {
  const [appDropdownOpen, setAppDropdownOpen] = useState(false);
  const { personaConfig } = usePersona();
  const router = useRouter();
  const t = useTranslations('nav');
  const [authUser, setAuthUser] = useState<string | null>(null);
  const [authEnabled, setAuthEnabled] = useState(false);
  // Entra-approved users get the user demo only (no administration).
  const [canAdmin, setCanAdmin] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/check');
      const data = await res.json();
      if (data.authEnabled) {
        setAuthEnabled(true);
        setAuthUser(data.username || null);
        setCanAdmin(data.role !== 'entra');
      }
    } catch {
      // Auth check failed silently
    }
  }, []);

  useEffect(() => {
    checkAuth();
    // Heartbeat: keep the server-side session marked active so it isn't
    // idle-evicted while a tab stays open without navigating.
    const heartbeat = setInterval(checkAuth, 4 * 60 * 1000);
    return () => clearInterval(heartbeat);
  }, [checkAuth]);

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
    router.refresh();
  }
  
  const hasDocuments = selectedApp?.files && selectedApp.files.length > 0;
  const hasSourcePages = selectedApp?.markdown_pages && selectedApp.markdown_pages.length > 0;
  
  // Automotive claims has its own overview with inline documents/timeline - hide these tabs
  const isAutomotiveClaims = personaConfig.id === 'automotive_claims';

  const getAppDisplayTitle = getApplicationDisplayTitle;

  const navItems = [
    { id: 'overview' as const, label: t('overview'), icon: LayoutDashboard, enabled: true },
    { id: 'timeline' as const, label: t('timeline'), icon: Clock, enabled: true, hidden: isAutomotiveClaims },
    { id: 'documents' as const, label: t('documents'), icon: FileText, enabled: hasDocuments, count: selectedApp?.files?.length, hidden: isAutomotiveClaims },
    { id: 'source' as const, label: t('sourcePages'), icon: FileStack, enabled: hasSourcePages, count: selectedApp?.markdown_pages?.length },
  ].filter(item => !item.hidden);

  const selectedApplication = applications.find(a => a.id === selectedAppId);

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      {/* Top Bar */}
      <div className="flex items-center justify-between gap-4 px-6 py-3">
        {/* Logo & Brand */}
        <div className="flex min-w-0 items-center gap-5">
          <Link href="/" className="flex min-w-0 items-center gap-3">
            <BrandMark />
          </Link>

          {/* Persona Selector */}
          <PersonaSelector />

          {/* Application Selector - Only in workbench view */}
          {showWorkbenchControls && applications.length > 0 && (
            <div className="relative">
              <button
                onClick={() => setAppDropdownOpen(!appDropdownOpen)}
                className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
              >
                <span className="text-slate-700">
                  {selectedApplication ? getAppDisplayTitle(selectedApplication) : t('selectApplication')}
                </span>
                <ChevronDown className={clsx('w-4 h-4 text-slate-400 transition-transform', appDropdownOpen && 'rotate-180')} />
              </button>

              {appDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setAppDropdownOpen(false)} />
                  <div className="absolute top-full left-0 mt-2 w-64 bg-white rounded-lg shadow-xl border border-slate-200 z-20 max-h-96 overflow-y-auto flex flex-col">
                    <div className="py-1 overflow-y-auto">
                      {applications.map((app) => (
                        <button
                          key={app.id}
                          onClick={() => {
                            onSelectApp(app.id);
                            setAppDropdownOpen(false);
                          }}
                          className={clsx(
                            'w-full text-left px-4 py-2 text-sm hover:bg-slate-50 transition-colors',
                            selectedAppId === app.id && 'font-medium'
                          )}
                          style={selectedAppId === app.id ? { color: brand.primary, backgroundColor: `${brand.primary}10` } : undefined}
                        >
                          <div className="font-medium truncate">
                            {getAppDisplayTitle(app)}
                          </div>
                          <div className="text-xs text-slate-500 flex items-center gap-2">
                            {app.external_reference || t('noReference')}
                            <StatusBadge status={app.status} />
                          </div>
                        </button>
                      ))}
                    </div>
                    {canAdmin && (
                    <div className="border-t border-slate-200 mt-auto">
                      <Link
                        href="/admin"
                        className="block w-full text-left px-4 py-2 text-sm transition-colors hover:bg-slate-50"
                        style={{ color: brand.primary }}
                        onClick={() => setAppDropdownOpen(false)}
                      >
                        {t('newApplication')}
                      </Link>
                    </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Right Side Actions */}
        <div className="flex min-w-0 flex-shrink items-center justify-end gap-2">
          {/* Glossary Dropdown - Only in workbench view */}
          {showWorkbenchControls && <GlossaryDropdown />}
          
          <Link
            href="/customers"
            className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <Users className="w-4 h-4" />
            <span>{t('customer360')}</span>
          </Link>
          {canAdmin && (
          <Link
            href="/admin"
            className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <Settings className="w-4 h-4" />
            <span>{t('admin')}</span>
          </Link>
          )}

          {/* Language Switcher */}
          <LanguageSwitcher />

          {/* Demo Guide */}
          <DemoGuideModal />

          {/* Auth: username & logout */}
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
                className="flex items-center gap-1.5 px-2.5 py-1.5 text-sm rounded-lg transition-colors"
                style={{ color: brand.primary, backgroundColor: `${brand.primary}0D` }}
                title={t('signOut')}
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Navigation Tabs */}
      {selectedApp && (
        <nav className="flex items-center gap-1 overflow-x-auto border-t border-slate-100 bg-slate-50/50 px-6">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => item.enabled && onChangeView(item.id)}
              disabled={!item.enabled}
              className={clsx(
                'flex shrink-0 items-center gap-2 border-b-2 -mb-px px-5 py-4 text-sm font-semibold transition-colors',
                activeView === item.id
                ? 'bg-white'
                  : item.enabled
                  ? 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
                  : 'border-transparent text-slate-400 cursor-not-allowed'
              )}
              style={activeView === item.id ? { color: brand.primary, borderColor: brand.primary } : undefined}
            >
              <item.icon className="w-4 h-4" />
              <span>{item.label}</span>
              {item.count !== undefined && item.count > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">
                  {item.count}
                </span>
              )}
            </button>
          ))}
        </nav>
      )}
    </header>
  );
}
