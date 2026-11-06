'use client';

import { Suspense, useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import LandingPage from '@/components/LandingPage';
import WorkbenchView from '@/components/WorkbenchView';
import TopNav from '@/components/TopNav';
import { usePersona } from '@/lib/PersonaContext';
import { ApplicationListItem } from '@/lib/types';
import { PersonaId, PERSONAS } from '@/lib/personas';
import { readCaseParams, writeCaseParams, type CaseView } from '@/lib/caseUrl';
import { useTranslations } from 'next-intl';

type ViewType = 'landing' | 'workbench';

/** Case opened from the address bar: deep link, or the same case after a reload (language switch). */
interface CaseLink {
  appId: string;
  conversationId: string | null;
  view: CaseView | null;
  page: number | null;
}

export default function Home() {
  return (
    <Suspense>
      <HomeContent />
    </Suspense>
  );
}

function HomeContent() {
  const t = useTranslations('dashboard');
  const [applications, setApplications] = useState<ApplicationListItem[]>([]);
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [view, setView] = useState<ViewType>('landing');
  const [username, setUsername] = useState<string | null>(null);
  const { currentPersona, setPersona, isLoading: personaLoading } = usePersona();
  const searchParams = useSearchParams();
  const [deepLinkHandled, setDeepLinkHandled] = useState(false);
  const [caseLink, setCaseLink] = useState<CaseLink | null>(null);
  const isFirstRender = useRef(true);

  const fetchUsername = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/check');
      const data = await res.json();
      if (data.authEnabled && data.username) {
        setUsername(data.username);
      }
    } catch {
      // Auth check failed silently
    }
  }, []);

  useEffect(() => {
    fetchUsername();
  }, [fetchUsername]);

  // Re-fetch applications when window regains focus (handles
  // deletions made in Admin or another tab).
  useEffect(() => {
    const onFocus = () => {
      if (view === 'landing') {
        fetchApplications();
      }
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [view, currentPersona]);

  const fetchApplications = async (persona?: string) => {
    const p = persona || currentPersona;
    try {
      setLoading(true);
      setLoadError(false);
      console.log('Loading applications for persona:', p);
      const response = await fetch(`/api/applications?persona=${p}`, {
        cache: 'no-store',
        headers: { 'Cache-Control': 'no-cache' },
      });
      if (response.ok) {
        const apps = await response.json();
        setApplications(apps);
        return apps;
      } else {
        throw new Error(`Application list request failed: ${response.status}`);
      }
    } catch (err) {
      console.error('Failed to load applications:', err);
      setLoadError(true);
      setApplications([]);
      return [];
    } finally {
      setLoading(false);
    }
  };

  // Case in the address bar (?app=…&persona=…&view=…&page=…&conversation=…), read once:
  // a link from another case's chat history, or the open case after a reload.
  useEffect(() => {
    if (personaLoading) return; // Wait for persona to load from localStorage
    if (deepLinkHandled) return;
    setDeepLinkHandled(true);
    const link = readCaseParams(searchParams.toString());

    if (link.app) {
      const appParam = link.app;
      setCaseLink({ appId: appParam, conversationId: link.conversation, view: link.view, page: link.page });

      if (link.persona && link.persona in PERSONAS) {
        setPersona(link.persona as PersonaId);
        // Fetch apps for the target persona, then select the app
        fetchApplications(link.persona).then(() => {
          setSelectedAppId(appParam);
          setView('workbench');
        });
      } else {
        // No persona specified, use current
        fetchApplications().then(() => {
          setSelectedAppId(appParam);
          setView('workbench');
        });
      }
    } else {
      fetchApplications();
    }
  }, [searchParams, personaLoading]);

  // The open case stays in the address bar, so that a reload — the language switch reloads
  // the page — reopens it instead of the dashboard (the workbench adds its tab and page).
  useEffect(() => {
    if (!deepLinkHandled) return;
    if (view === 'workbench' && selectedAppId) {
      writeCaseParams({ app: selectedAppId, persona: currentPersona, conversation: null });
    } else {
      writeCaseParams({ app: null, persona: null, view: null, page: null, conversation: null });
    }
  }, [deepLinkHandled, view, selectedAppId, currentPersona]);

  useEffect(() => {
    // Skip first render (initial load handled by deep-link or searchParams effect)
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    // Always reset view to landing when persona changes
    setView('landing');
    setSelectedAppId(null);
    setApplications([]);  // Clear immediately to prevent flash of old persona data
    fetchApplications();
  }, [currentPersona]);

  const handleSelectApp = (appId: string) => {
    setSelectedAppId(appId);
    setView('workbench');
  };

  const handleBackToLanding = () => {
    setView('landing');
    setSelectedAppId(null);
    fetchApplications();
  };

  if (view === 'workbench' && selectedAppId) {
    const restore = caseLink?.appId === selectedAppId ? caseLink : null;
    return (
      <WorkbenchView 
        applicationId={selectedAppId}
        applications={applications}
        onBack={handleBackToLanding}
        onSelectApp={handleSelectApp}
        initialConversationId={restore?.conversationId ?? null}
        initialView={restore?.view ?? null}
        initialPage={restore?.page ?? null}
      />
    );
  }

  // Landing Page View
  return (
    <>
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <TopNav 
             applications={applications}
             selectedAppId={undefined}
             activeView="overview"
             onSelectApp={handleSelectApp}
             onChangeView={() => {}}
             showWorkbenchControls={false}
        />
      </header>
      {loadError && (
        <div role="alert" className="mx-6 mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {t('loadError')}
        </div>
      )}
      <LandingPage 
        applications={applications}
        onSelectApp={handleSelectApp}
        onRefreshApps={fetchApplications}
        loading={loading}
        username={username}
      />
    </>
  );
}
