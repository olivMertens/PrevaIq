'use client';

import Link from 'next/link';
import {
  LayoutDashboard,
  Clock,
  FileText,
  FileStack,
  ChevronDown,
  Users,
  CloudSun,
  ListChecks,
  Activity,
} from 'lucide-react';
import type { ApplicationListItem, ApplicationMetadata } from '@/lib/types';
import clsx from 'clsx';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import PersonaSelector from './PersonaSelector';
import GlossaryDropdown from './GlossaryDropdown';
import { brand } from '@/lib/brand';
import { usePersona } from '@/lib/PersonaContext';
import { useLocale, useTranslations } from 'next-intl';
import UserMenu from './UserMenu';
import BrandMark from './BrandMark';
import StatusBadge from './landing/StatusBadge';
import CaseTitle from './case/CaseTitle';
import { getApplicationDisplayTitle } from '@/lib/applicationDisplay';
import { compactAuthIdentity } from '@/lib/displayText';
import type { CaseView } from '@/lib/caseUrl';
import { CLAIM_VIEWS, isClaimsWorkspace } from '@/lib/claimsWorkspace';

interface TopNavProps {
  applications: ApplicationListItem[];
  selectedAppId?: string;
  selectedApp?: ApplicationMetadata;
  activeView: CaseView;
  onSelectApp: (appId: string) => void;
  onChangeView: (view: CaseView) => void;
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
  const locale = useLocale();
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
  
  const claimsWorkspace = isClaimsWorkspace(personaConfig.id);

  const getAppDisplayTitle = (app: ApplicationListItem) => getApplicationDisplayTitle(app, locale);

  const claimsIcons = { overview: LayoutDashboard, documents: FileText, analysis: ListChecks, customer: Users, weather: CloudSun, timeline: Clock };
  const navItems = claimsWorkspace ? CLAIM_VIEWS.map((id) => ({
    id, label: t(`claims.${id}`), icon: claimsIcons[id], enabled: true,
    count: id === 'documents' ? selectedApp?.files?.length : undefined,
  })) : [
    { id: 'overview' as const, label: t('overview'), icon: LayoutDashboard, enabled: true },
    { id: 'timeline' as const, label: t('timeline'), icon: Clock, enabled: true },
    { id: 'documents' as const, label: t('documents'), icon: FileText, enabled: hasDocuments, count: selectedApp?.files?.length },
    { id: 'source' as const, label: t('sourcePages'), icon: FileStack, enabled: hasSourcePages, count: selectedApp?.markdown_pages?.length },
  ];

  const selectedApplication = applications.find(a => a.id === selectedAppId);
  const authUserLabel = compactAuthIdentity(authUser);

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-3 xl:gap-x-4 xl:px-6">
        {/* Logo & Brand */}
        <div className="flex min-w-[18rem] flex-1 items-center gap-3 md:min-w-0 xl:gap-5">
          <Link href="/" className="flex flex-shrink-0 items-center gap-3">
            <BrandMark />
          </Link>

          {/* Persona Selector */}
          <PersonaSelector />

          {/* Application Selector - Only in workbench view */}
          {showWorkbenchControls && applications.length > 0 && (
            <div className="relative min-w-0">
              <button
                onClick={() => setAppDropdownOpen(!appDropdownOpen)}
                className="flex w-full min-w-0 max-w-[12.5rem] items-center gap-2 px-3 py-2 text-sm bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors shadow-sm lg:max-w-[16rem] xl:max-w-[18rem] 2xl:max-w-[26rem]"
              >
                {selectedApplication ? (
                  // The breadcrumb below shows holder and subject; here the subject only fits on 2xl.
                  <CaseTitle
                    title={getAppDisplayTitle(selectedApplication)}
                    className="min-w-0 text-slate-700"
                    subjectClassName="hidden 2xl:inline"
                  />
                ) : (
                  <span className="truncate text-slate-700">{t('selectApplication')}</span>
                )}
                <ChevronDown className={clsx('w-4 h-4 flex-shrink-0 text-slate-400 transition-transform', appDropdownOpen && 'rotate-180')} />
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
                          style={selectedAppId === app.id ? { color: brand.ink, backgroundColor: `${brand.primary}10` } : undefined}
                        >
                          <CaseTitle title={getAppDisplayTitle(app)} className="font-medium" />
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
                        style={{ color: brand.ink }}
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

        {/* Right Side Actions: language, demo guide, admin and sign-out live in the user menu */}
        <div className="ml-auto flex flex-shrink-0 items-center justify-end gap-1.5 xl:gap-2">
          {/* Glossary Dropdown - Only in workbench view */}
          {showWorkbenchControls && <GlossaryDropdown />}
          
          <Link
            href="/customers"
            aria-label={t('customer360')}
            title={t('customer360')}
            className="flex items-center gap-2 px-2.5 py-2 text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors xl:px-3"
          >
            <Users className="w-4 h-4" aria-hidden />
            <span className="hidden whitespace-nowrap xl:inline">{t('customer360')}</span>
          </Link>

          <UserMenu
            user={authUser}
            userLabel={authUserLabel}
            canAdmin={canAdmin}
            onSignOut={authEnabled ? handleLogout : undefined}
          />
        </div>
      </div>

      {/* Navigation Tabs */}
      {selectedApp && (
        <nav aria-label={t('claims.navigation')} className="flex flex-wrap items-center gap-1 border-t border-slate-100 bg-slate-50/50 px-4">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => item.enabled && onChangeView(item.id)}
              disabled={!item.enabled}
              aria-current={activeView === item.id ? 'page' : undefined}
              className={clsx(
                'flex shrink-0 items-center gap-2 border-b-2 -mb-px px-3 py-3 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600',
                activeView === item.id
                ? 'bg-white'
                  : item.enabled
                  ? 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
                  : 'border-transparent text-slate-400 cursor-not-allowed'
              )}
              style={activeView === item.id ? { color: brand.ink, borderColor: brand.primary } : undefined}
            >
              <item.icon className="w-4 h-4" aria-hidden />
              <span>{item.label}</span>
              {item.count !== undefined && item.count > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-slate-200 text-slate-600 text-xs rounded">
                  {item.count}
                </span>
              )}
            </button>
          ))}
          {claimsWorkspace && (
            <details className="relative ml-auto">
              <summary className={clsx('cursor-pointer rounded-lg px-3 py-2 text-sm font-medium', ['source', 'data', 'pipeline'].includes(activeView) ? 'bg-indigo-50 text-indigo-800' : 'text-slate-600')}>
                {t('claims.more')}
              </summary>
              <div className="absolute right-0 top-full z-50 mt-1 min-w-56 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                {([
                  { id: 'source', label: t('sourcePages'), Icon: FileStack, enabled: hasSourcePages },
                  { id: 'data', label: t('claims.data'), Icon: ListChecks, enabled: true },
                  { id: 'pipeline', label: t('claims.pipeline'), Icon: Activity, enabled: true },
                ] as const).map(({ id, label, Icon, enabled }) => (
                  <button key={id} type="button" disabled={!enabled} aria-current={activeView === id ? 'page' : undefined}
                    className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                    onClick={(event) => { onChangeView(id); event.currentTarget.closest('details')?.removeAttribute('open'); }}>
                    <Icon className="h-4 w-4" aria-hidden />{label}
                  </button>
                ))}
              </div>
            </details>
          )}
        </nav>
      )}
    </header>
  );
}
