'use client';

import { useState, useEffect, useRef } from 'react';
import { Sparkles, FileText, ChevronLeft, Loader2, Activity } from 'lucide-react';
import TopNav from '@/components/TopNav';
import PatientHeader from '@/components/PatientHeader';
import PatientSummary from '@/components/PatientSummary';
import LabResultsPanel from '@/components/LabResultsPanel';
import SubstanceUsePanel from '@/components/SubstanceUsePanel';
import FamilyHistoryPanel from '@/components/FamilyHistoryPanel';
import AllergiesPanel from '@/components/AllergiesPanel';
import OccupationPanel from '@/components/OccupationPanel';
import ChronologicalOverview from '@/components/ChronologicalOverview';
import DocumentsPanel from '@/components/DocumentsPanel';
import SourcePagesPanel from '@/components/SourcePagesPanel';
import BatchSummariesPanel from '@/components/BatchSummariesPanel';
import SourceReviewView from '@/components/SourceReviewView';
import LoadingSpinner from '@/components/LoadingSpinner';
import PolicySummaryPanel from '@/components/PolicySummaryPanel';
import SouscriaContextPanel from '@/components/SouscriaContextPanel';
import PolicyReportModal from '@/components/PolicyReportModal';
import ChatDrawer from '@/components/ChatDrawer';
import PipelineStatusPill from '@/components/case/PipelineStatusPill';
import CaseTitle from '@/components/case/CaseTitle';
import BodySystemDeepDiveModal from '@/components/BodySystemDeepDiveModal';
import LifeHealthClaimsOverview from '@/components/claims/LifeHealthClaimsOverview';
import PropertyCasualtyClaimsOverview from '@/components/claims/PropertyCasualtyClaimsOverview';
import AutomotiveClaimsWorkspace from '@/components/claims/AutomotiveClaimsWorkspace';
import { isClaimsWorkspace } from '@/lib/claimsWorkspace';
import UnderwritingDecisionFooter from '@/components/UnderwritingDecisionFooter';
import { MortgageWorkbench } from '@/components/mortgage';
import { usePersona } from '@/lib/PersonaContext';
import { useToast } from '@/lib/ToastProvider';
import { useLocale, useTranslations } from 'next-intl';
import { getApplication, runRiskAnalysis } from '@/lib/api';
import { getApplicationDisplayTitle } from '@/lib/applicationDisplay';
import { writeCaseParams, type CaseView } from '@/lib/caseUrl';
import type { ApplicationMetadata, ApplicationListItem } from '@/lib/types';

type ViewType = CaseView;

interface WorkbenchViewProps {
  applicationId: string;
  applications: ApplicationListItem[];
  onBack: () => void;
  onSelectApp: (appId: string) => void;
  /** Chat conversation to reopen (link from another case's chat history). */
  initialConversationId?: string | null;
  /** Tab and source page to reopen (address bar after a reload, e.g. a language switch). */
  initialView?: ViewType | null;
  initialPage?: number | null;
}

export default function WorkbenchView({ 
  applicationId, 
  applications, 
  onBack,
  onSelectApp,
  initialConversationId,
  initialView,
  initialPage,
}: WorkbenchViewProps) {
  const [selectedApp, setSelectedApp] = useState<ApplicationMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<ViewType>('overview');
  const [isPolicyReportOpen, setIsPolicyReportOpen] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(!!initialConversationId);
  const [isDeepDiveOpen, setIsDeepDiveOpen] = useState(false);
  const [sourcePageNumber, setSourcePageNumber] = useState<number | undefined>(undefined);
  // Page being read in Documents & Pages, kept in the address bar with the tab.
  const [readingPage, setReadingPage] = useState<number | null>(null);
  // Applied once, when the first case loads; another case opens on its overview.
  const restore = useRef({ view: initialView ?? null, page: initialPage ?? null });
  const { currentPersona, personaConfig } = usePersona();
  const locale = useLocale();
  const tw = useTranslations('workbench');
  const { addToast } = useToast();

  // Load application details
  useEffect(() => {
    async function loadApp() {
      if (!applicationId) return;
      
      try {
        setLoading(true);
        setError(null);
        console.log('Loading application:', applicationId);
        const app = await getApplication(applicationId);
        setSelectedApp(app);
        // Reset view when app changes (or reopen the tab and page of the address bar)
        const { view, page } = restore.current;
        restore.current = { view: null, page: null };
        setActiveView(view ?? 'overview');
        setSourcePageNumber(page ?? undefined);
        setReadingPage(null);
      } catch (err) {
        console.error('Failed to load application:', err);
        setError(tw('applicationLoadError'));
        addToast('error', tw('applicationLoadError'));
      } finally {
        setLoading(false);
      }
    }
    
    loadApp();
  }, [applicationId]);

  const loadedAppId = selectedApp?.id;
  useEffect(() => {
    if (!loadedAppId) return;
    writeCaseParams({
      view: activeView === 'overview' ? null : activeView,
      page: activeView === 'source' ? readingPage : null,
    });
  }, [loadedAppId, activeView, readingPage]);

  // Poll for status updates if application is processing
  const lastProcessingTime = useRef(0);
  useEffect(() => {
    if (!selectedApp) return;

    if (selectedApp.processing_status) {
      lastProcessingTime.current = Date.now();
    }

    // Continue polling during processing OR for 8s after it ends (grace period
    // to catch brief null gaps between extraction→analysis transitions)
    const shouldPoll = selectedApp.processing_status ||
                       (lastProcessingTime.current > 0 && Date.now() - lastProcessingTime.current < 8000);
    if (!shouldPoll) return;
    
    const appId = selectedApp.id;
    const interval = setInterval(async () => {
      try {
        const updatedApp = await getApplication(appId);
        if (updatedApp.id !== appId) return;

        // End grace polling after timeout
        if (!updatedApp.processing_status && Date.now() - lastProcessingTime.current >= 8000) {
          clearInterval(interval);
        }

        if (updatedApp.status !== selectedApp.status || updatedApp.processing_status !== selectedApp.processing_status) {
            setSelectedApp(updatedApp);
        }
      } catch (err) {
        console.error('Polling failed:', err);
      }
    }, 2000);
    
    return () => clearInterval(interval);
  }, [selectedApp]);

  // In a new language the analysis is shown as generated while the API translates it;
  // the translated case replaces it as soon as it is ready (bounded: 3 minutes).
  const pendingLanguage = selectedApp?.analysis_translation_pending;
  const selectedAppId = selectedApp?.id;
  useEffect(() => {
    if (!pendingLanguage || !selectedAppId) return;
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      if (attempts >= 60) clearInterval(timer);
      try {
        const updated = await getApplication(selectedAppId);
        if (!updated.analysis_translation_pending) {
          clearInterval(timer);
          setSelectedApp((current) => (current?.id === updated.id ? updated : current));
        }
      } catch {
        // The analysis stays as it is; the next attempt may succeed.
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [pendingLanguage, selectedAppId]);

  const renderContent = () => {
    if (!selectedApp) return null;

    if (isClaimsWorkspace(currentPersona)) {
      return (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className={activeView === 'source' ? 'hidden' : 'flex min-h-0 flex-1 flex-col'}>
            {currentPersona === 'automotive_claims' ? (
              <AutomotiveClaimsWorkspace key={selectedApp.id} application={selectedApp} view={activeView}
                onChangeView={setActiveView} onApplicationUpdate={setSelectedApp} />
            ) : (
              <PropertyCasualtyClaimsOverview application={selectedApp} onApplicationUpdate={setSelectedApp}
                view={activeView} onChangeView={setActiveView} />
            )}
          </div>
          {activeView === 'source' && <SourceReviewView application={selectedApp} initialPage={sourcePageNumber} onPageChange={setReadingPage} />}
        </div>
      );
    }

    switch (activeView) {
      case 'timeline':
        return (
          <div className="flex-1 overflow-auto p-6">
            <ChronologicalOverview application={selectedApp} fullWidth persona={currentPersona} />
          </div>
        );
      case 'documents':
        return (
          <div className="flex-1 overflow-auto p-6">
            <DocumentsPanel files={selectedApp.files || []} applicationId={selectedApp.id} />
          </div>
        );
      case 'source':
        return <SourceReviewView application={selectedApp} initialPage={sourcePageNumber} onPageChange={setReadingPage} />;
      case 'overview':
      default:
        if (currentPersona === 'life_health_claims') {
          return <LifeHealthClaimsOverview application={selectedApp} />;
        }
        if (currentPersona === 'mortgage') {
          return <MortgageWorkbench applicationId={selectedApp.id} />;
        }
        // Default: Underwriting overview
        return renderUnderwritingOverview();
    }
  };

  const renderUnderwritingOverview = () => {
    if (!selectedApp) return null;
    
    const handleRerunAnalysis = async () => {
      if (!selectedApp) return;
      try {
        const app = await runRiskAnalysis(selectedApp.id, 300000, 2000, locale);
        setSelectedApp(app);
      } catch (err) {
        console.error('Failed to re-run risk analysis:', err);
        addToast('error', err instanceof Error ? err.message : tw('riskAnalysisError'));
      }
    };
    
    return (
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {/* Decision bar — sticky at top */}
        <UnderwritingDecisionFooter
          applicationId={selectedApp.id}
          position="top"
          riskLevel={selectedApp.risk_analysis?.parsed?.overall_risk_level}
          onDecisionSubmitted={async () => {
            const app = await getApplication(selectedApp.id);
            setSelectedApp(app);
          }}
        />
        <div className="flex-1 min-h-0 overflow-auto p-6">
        <div className="w-full space-y-6">
          <div className="relative">
            <div className="pr-[340px]">
              <div className="flex flex-col gap-6">
                <PatientSummary 
                  application={selectedApp} 
                  onPolicyClick={(policyId) => {
                    setIsPolicyReportOpen(true);
                  }}
                  onDeepDive={() => setIsDeepDiveOpen(true)}
                />
                <PolicySummaryPanel
                  application={selectedApp}
                  onViewFullReport={() => setIsPolicyReportOpen(true)}
                  onRiskAnalysisComplete={async () => {
                     const app = await getApplication(selectedApp.id);
                     setSelectedApp(app);
                  }}
                />
                <SouscriaContextPanel application={selectedApp} />
              </div>
            </div>
            <div className="absolute top-0 right-0 bottom-0 w-80">
              <ChronologicalOverview application={selectedApp} persona={currentPersona} />
            </div>
          </div>

          <div className="flex items-center gap-4 py-2">
            <div className="flex-1 border-t border-slate-200" />
            <div className="flex items-center gap-2 text-xs font-medium text-slate-400 uppercase tracking-wider">
              <FileText className="w-4 h-4" />
              <span>{tw('evidenceFromDocuments')}</span>
            </div>
            <div className="flex-1 border-t border-slate-200" />
          </div>

          <div className="grid grid-cols-3 gap-6">
            <LabResultsPanel application={selectedApp} />
            <SubstanceUsePanel application={selectedApp} />
            <FamilyHistoryPanel application={selectedApp} />
          </div>

          <div className="grid grid-cols-2 gap-6">
            <AllergiesPanel application={selectedApp} />
            <OccupationPanel application={selectedApp} />
          </div>
        </div>
        
        <PolicyReportModal
          isOpen={isPolicyReportOpen}
          onClose={() => setIsPolicyReportOpen(false)}
          application={selectedApp}
          onRerunAnalysis={handleRerunAnalysis}
        />
        
        <BodySystemDeepDiveModal
          isOpen={isDeepDiveOpen}
          onClose={() => setIsDeepDiveOpen(false)}
          application={selectedApp}
          onNavigateToPage={(page) => {
            setIsDeepDiveOpen(false);
            setSourcePageNumber(page);
            setActiveView('source');
          }}
          onApplicationUpdate={(app) => {
            setSelectedApp(app);
          }}
        />
      </div>
      </div>
    );
  };

  return (
    <div className="h-screen min-h-0 bg-gradient-to-br from-slate-50 to-slate-100 flex flex-col overflow-hidden">
      {/* Navigation */}
      <div className="z-50 bg-white flex-shrink-0">
        <TopNav 
          applications={applications}
          selectedAppId={selectedApp?.id}
          selectedApp={selectedApp || undefined}
          activeView={activeView}
          onSelectApp={onSelectApp}
          onChangeView={setActiveView}
          showWorkbenchControls={true}
        />
        
        {/* Back Button / Breadcrumb + AI pipeline status */}
        <div className="border-b border-slate-200 px-6 py-2 flex items-center gap-2 bg-white/95 backdrop-blur-sm">
            <button 
                onClick={onBack}
                className="flex flex-shrink-0 items-center text-sm text-slate-500 hover:text-indigo-600 transition-colors"
            >
                <ChevronLeft className="w-4 h-4 mr-1" />
                {tw('returnToDashboard')}
            </button>
            <span className="text-slate-300" aria-hidden>/</span>
            {selectedApp ? (
              <CaseTitle
                title={getApplicationDisplayTitle(selectedApp, locale)}
                className="min-w-0 text-sm font-medium text-slate-700"
              />
            ) : (
              <span className="min-w-0 truncate text-sm font-medium text-slate-700">
                {tw('applicationDetails')}
              </span>
            )}
             {loading && <span className="ml-1 text-xs text-slate-400 animate-pulse">{tw('loading')}</span>}
            {selectedApp && (
              <div className="ml-auto flex flex-shrink-0 items-center gap-3 pl-2">
                {selectedApp.analysis_translation_pending && (
                  <span role="status" className="hidden items-center gap-1.5 text-xs text-indigo-700 md:flex">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                    {tw('translatingAnalysis')}
                  </span>
                )}
                {selectedApp.analysis_translation_failed && (
                  <span role="status" className="hidden text-xs text-amber-800 md:inline">
                    {tw('analysisTranslationFailed')}
                  </span>
                )}
                <PipelineStatusPill application={selectedApp} />
              </div>
            )}
        </div>
      </div>

      <main className="flex flex-col flex-1 relative overflow-hidden min-h-0">
          {loading ? (
            <div className="flex-1 flex items-center justify-center">
                <LoadingSpinner />
            </div>
          ) : error ? (
            <div className="flex-1 flex items-center justify-center">
                 <div className="text-center text-rose-600 bg-white p-6 rounded-xl shadow-sm border border-rose-100">
                    <p>{error}</p>
                    <button onClick={onBack} className="mt-4 text-sm text-slate-500 hover:text-indigo-600 underline">{tw('returnToList')}</button>
                 </div>
            </div>
          ) : selectedApp ? (
            <>
               {/* Processing progress banner — always mounted, hidden via CSS transition */}
               <div className={`border-b px-6 flex items-center gap-3 transition-all duration-300 overflow-hidden ${
                 selectedApp.processing_status
                   ? selectedApp.processing_status === 'analyzing'
                     ? 'max-h-14 py-3 opacity-100 bg-violet-50 border-violet-200'
                     : 'max-h-14 py-3 opacity-100 bg-sky-50 border-sky-200'
                   : 'max-h-0 py-0 opacity-0 border-transparent'
               }`}>
                   {selectedApp.processing_status === 'analyzing' ? (
                     <Activity className="w-4 h-4 text-violet-600 animate-pulse flex-shrink-0" />
                   ) : (
                     <Loader2 className="w-4 h-4 text-sky-600 animate-spin flex-shrink-0" />
                   )}
                   <div className="flex items-center gap-2 flex-1 min-w-0">
                     <span className={`text-sm font-medium ${
                       selectedApp.processing_status === 'analyzing' ? 'text-violet-700' : 'text-sky-700'
                     }`}>
                       {selectedApp.processing_status === 'extracting'
                         ? tw('extractionAgentRunning')
                         : tw('analysisAgentRunning')}
                     </span>
                     <span className="flex gap-1 ml-1">
                       <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                       <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                       <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                     </span>
                   </div>
                   <span className="text-xs bg-sky-100 text-sky-600 px-2 py-0.5 rounded-full font-medium flex-shrink-0">{tw('live')}</span>
               </div>
               {currentPersona === 'underwriting' && <PatientHeader application={selectedApp} />}
               {renderContent()}
            </>
          ) : null}
      </main>

      {selectedApp && (
        <ChatDrawer
          isOpen={isChatOpen}
          onClose={() => setIsChatOpen(false)}
          onOpen={() => setIsChatOpen(true)}
          applicationId={selectedApp.id}
          persona={currentPersona}
          contextLabels={selectedApp.context_labels}
          contextTasks={selectedApp.context_tasks}
          applicationStatus={selectedApp.status}
          processingStatus={selectedApp.processing_status}
          hasDecision={!!(selectedApp.llm_outputs as Record<string, unknown> | undefined)?.decision}
          caseTitle={getApplicationDisplayTitle(selectedApp, locale)}
          initialConversationId={initialConversationId}
        />
      )}
    </div>
  );
}
