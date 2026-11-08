'use client';

import { useCallback, useMemo, useState } from 'react';
import { Loader2, TriangleAlert, X } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { getApplication, type FraudAnalysisResponse } from '@/lib/api';
import type { ApplicationMetadata } from '@/lib/types';
import GalleryLightbox from '../GalleryLightbox';
import AttentionList, { type Density } from '@/components/case/AttentionList';
import CaseFacts from '@/components/case/CaseFacts';
import DecisionDialog, { type DecisionDraft } from '@/components/case/DecisionDialog';
import ClaimAnalysisSections from '@/components/case/ClaimAnalysisSections';
import ChronologicalOverview from '@/components/ChronologicalOverview';
import EvidenceStrip from '@/components/case/EvidenceStrip';
import LatestUpdates from '@/components/case/LatestUpdates';
import WeatherEvidencePanel from '@/components/case/WeatherEvidencePanel';
import AuroraEvidenceSummary from '@/components/case/AuroraEvidenceSummary';
import NextSteps from '@/components/case/NextSteps';
import VerdictBar from '@/components/case/VerdictBar';
import type { CaseSignal, DeepDiveTab } from '@/components/case/caseSignals';
import type { RecommendationId } from '@/components/case/recommendation';
import { usePersistentChoice, usePreviousVisit } from '@/components/case/usePersistentState';
import FraudAnalysisPanel from './FraudAnalysisPanel';
import { generateNoteDeReglement } from './generateNoteDeReglement';
import AnalysisLaunchDialog from './property/AnalysisLaunchDialog';
import PropertyDeepDive from './property/PropertyDeepDive';
import type { CaseView } from '@/lib/caseUrl';
import { claimCommunicationStatus, claimViewForDetail, savedClaimFraud } from '@/lib/claimsWorkspace';
import { useToast } from '@/lib/ToastProvider';
import { getFieldValue } from './property/propertyClaimHelpers';
import { useAnalysisRun } from './property/useAnalysisRun';
import { useFileUpload } from './property/useFileUpload';
import { usePropertyClaimData } from './property/usePropertyClaimData';
import { usePropertyCockpit } from './property/usePropertyCockpit';

interface PropertyCasualtyClaimsOverviewProps {
  application: ApplicationMetadata | null;
  onApplicationUpdate?: (app: ApplicationMetadata) => void;
  view?: CaseView;
  onChangeView: (view: CaseView) => void;
}

interface FraudStatus {
  isLoading: boolean;
  progress: number;
  error?: string | null;
}

const DENSITIES: readonly Density[] = ['essential', 'detailed'];
const DRAFT_STEP_KEYS = ['contact_client'];
const IDLE_FRAUD: FraudStatus = { isLoading: false, progress: 0 };
/** Where "Why?" leads: the evidence behind each recommendation. */
const WHY_TAB: Record<RecommendationId, DeepDiveTab> = {
  escalate_siu: 'fraud',
  request_expertise: 'fraud',
  approve_with_expertise: 'cover',
  stp_approve: 'summary',
  approve_standard: 'summary',
};

/**
 * Property claim cockpit: verdict first, then what needs attention, the next steps and
 * what changed; every detail opens on demand in the deep-dive drawer.
 */
function PropertyCockpit({ application, onApplicationUpdate, view = 'overview', onChangeView }: PropertyCasualtyClaimsOverviewProps) {
  const t = useTranslations('claims');
  const tReport = useTranslations('claims.report.note');
  const tc = useTranslations('caseCockpit');
  const locale = useLocale();
  const { addToast } = useToast();

  const data = usePropertyClaimData(application);
  const run = useAnalysisRun(application, onApplicationUpdate);
  const upload = useFileUpload(application, onApplicationUpdate);
  const [density, setDensity] = usePersistentChoice<Density>('prevaiq.cockpit.density', 'essential', DENSITIES);
  const previousVisit = usePreviousVisit(application?.id);

  const [checked, setChecked] = useState<number[]>([]);
  const [focus, setFocus] = useState<DeepDiveTab>('summary');
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [launchOpen, setLaunchOpen] = useState(false);
  const [decision, setDecision] = useState<{ open: boolean; draft: DecisionDraft | null }>({ open: false, draft: null });
  const [fraudOpen, setFraudOpen] = useState(false);
  const [fraudStartRequest, setFraudStartRequest] = useState(0);
  const [fraudStatus, setFraudStatus] = useState<FraudStatus>(IDLE_FRAUD);
  // The case carries the fraud analysis in the UI language; a fresh run wins until the case
  // is reloaded with it.
  const appFraud = useMemo(() => savedClaimFraud(application), [application]);
  const [runFraud, setRunFraud] = useState<FraudAnalysisResponse | null>(null);
  const fraudResult =
    runFraud && runFraud.analysis_timestamp !== appFraud?.analysis_timestamp ? runFraud : appFraud ?? runFraud;
  const appFraudStamp = appFraud?.analysis_timestamp;
  const applicationId = application?.id;

  const refresh = useCallback(() => {
    if (applicationId && onApplicationUpdate) {
      getApplication(applicationId).then(onApplicationUpdate).catch(() => addToast('error', tc('workspace.refreshError')));
    }
  }, [applicationId, onApplicationUpdate, addToast, tc]);

  const handleFraudComplete = useCallback((result: FraudAnalysisResponse) => {
    if (result.analysis_timestamp === appFraudStamp) return;
    setRunFraud(result);
    refresh();
  }, [appFraudStamp, refresh]);

  const handleFraudStatus = useCallback(({ isLoading, progress, error }: FraudStatus) => {
    setFraudStatus((current) =>
      current.isLoading === isLoading && current.progress === progress && current.error === error ? current : { isLoading, progress, error },
    );
  }, []);

  const cockpit = usePropertyCockpit({
    application,
    data,
    fraud: fraudResult,
    fraudStatus,
    analyzing: run.analyzing,
    checkedCount: checked.length,
  });

  const openTab = useCallback((tab: DeepDiveTab) => {
    setFocus(tab);
    onChangeView(claimViewForDetail(tab));
  }, [onChangeView]);
  const closeDecision = useCallback(() => setDecision((current) => ({ ...current, open: false })), []);
  const closeLaunch = useCallback(() => setLaunchOpen(false), []);
  const closeLightbox = useCallback(() => setLightboxIndex(null), []);
  const toggleStep = useCallback((index: number) => {
    setChecked((current) => (current.includes(index) ? current.filter((value) => value !== index) : [...current, index]));
  }, []);
  const { launch } = run;
  const launchAnalysis = useCallback(async () => {
    if (await launch()) setLaunchOpen(false);
  }, [launch]);

  if (!application) return null;

  const { recommendation } = cockpit;
  const { ef, steps } = data;
  const claimDate = getFieldValue(ef, ['DateSinistre', 'ClaimDate', 'DateEvenement']);
  const fieldCount = Object.values(ef).filter((entry) => entry?.value != null && entry.value !== '').length;
  const relaunch = () => {
    setLaunchOpen(true);
  };
  const openFraudReport = () => {
    setFraudOpen(true);
  };
  const startFraud = () => {
    if (!fraudStatus.isLoading) setFraudStartRequest((current) => current + 1);
  };
  const validate = () => {
    if (!recommendation) return;
    setDecision({
      open: true,
      draft: { decision: recommendation.decision, notes: `${recommendation.title} — ${recommendation.reason}` },
    });
  };

  const generateSettlement = () => {
    if (cockpit.settlement !== 'ready') return;
    const field = (keys: string[], fallback = '') => getFieldValue(ef, keys, fallback);
    generateNoteDeReglement({
      applicationId: application.id,
      insuredName: field(['InsuredName', 'NomAssure', 'NomSouscripteur']),
      policyNumber: field(['PolicyNumber', 'NumeroPolice', 'NumeroContrat']),
      claimNumber: field(['ClaimNumber', 'NumeroSinistre'], application.id),
      claimDate: field(['ClaimDate', 'DateSinistre', 'DateEvenement']),
      causeOfLoss: field(['CauseOfLoss', 'NatureSinistre', 'CauseDuSinistre'], t('defaults.waterOrStorm')),
      propertyAddress: field(['PropertyAddress', 'AdresseRisque', 'AdresseBien']),
      lineOfBusiness: field(['LineOfBusiness', 'NatureContrat', 'BrancheAssurance'], 'Habitation MRH'),
      totalEstimated: field(['TotalIncurred', 'MontantEstime', 'MontantTotal', 'MontantDevis', 'MontantReparation'], '—'),
      // The 250 € fallback is the French standard deductible; other currencies show none.
      deductible: field(['FranchiseApplicable', 'Franchise'], data.currency === 'EUR' ? '250 €' : '—'),
      settlementAmount: field(['SettlementAmount', 'MontantIndemnisation', 'IndemniteRecommandee']),
      aiSummary: data.aiSummary,
      extractedFields: ef as Record<string, { field_name?: string; value?: unknown; confidence?: number }>,
      llmOutputs: data.llmOutputs,
      files: data.files.map((file) => ({ filename: file.filename })),
      tasks: steps.map((step, index) => ({ task: step.task, done: checked.includes(index) })),
    }, tReport, locale);
  };

  const details = (tab: DeepDiveTab) => (
    <PropertyDeepDive tab={tab} application={application} data={data} fraud={fraudResult}
      fraudStatus={fraudStatus} analyzing={run.analyzing} estimatedAmount={cockpit.amount}
      decisionStatus={claimCommunicationStatus(application)}
      upload={upload} onRelaunch={relaunch} onOpenFraudReport={openFraudReport}
      onRunFraud={startFraud} onOpenFile={setLightboxIndex} onRefresh={refresh} />
  );
  const facts = (
    <CaseFacts facts={cockpit.facts} fieldCount={fieldCount} linkedCustomerId={application.external_reference}
      onOpenData={() => openTab('data')} onOpenCustomer={() => openTab('customer')} />
  );

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-slate-100">
      <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4 pb-24">
        {view === 'overview' && <VerdictBar
          identity={cockpit.identity}
          recommendation={recommendation}
          criticalCount={cockpit.criticalCount}
          recordedDecision={cockpit.recordedDecision}
          analysisRunning={run.analyzing}
          amount={cockpit.amountKpi}
          fraud={cockpit.fraudKpi}
          cover={cockpit.cover}
          customer={cockpit.customer}
          onValidate={validate}
          onOtherDecision={() => setDecision({ open: true, draft: null })}
          onWhy={() => openTab(recommendation ? WHY_TAB[recommendation.id] : 'summary')}
          onRunAnalysis={() => setLaunchOpen(true)}
          onOpenTab={openTab}
          onRunFraud={startFraud}
          web={fraudResult?.web_intelligence}
        />}

        {run.error && !launchOpen && (
          <div role="alert" className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
            <TriangleAlert className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
            <p className="min-w-0 flex-1">{run.error}</p>
            <button type="button" onClick={() => run.setError(null)} aria-label={tc('dismiss')} className="rounded p-0.5 hover:bg-rose-100">
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        )}
        {upload.uploading && (
          <p role="status" className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm text-indigo-900">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            {upload.progressMessage}
          </p>
        )}
        {fraudStatus.error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">{fraudStatus.error}</p>}
        {view !== 'overview' && fraudStatus.isLoading && <p role="status" className="rounded-lg bg-purple-50 p-3 text-sm text-purple-900">{tc('kpi.analyzing', { progress: fraudStatus.progress })}</p>}
        {view === 'analysis' && <ClaimAnalysisSections focus={focus} facts={facts} renderSection={details} />}
        {view === 'customer' && <div className="rounded-xl border border-slate-200 bg-white p-5">{details('customer')}</div>}
        {view === 'documents' && <div className="rounded-xl border border-slate-200 bg-white p-5">{details('evidence')}</div>}
        {view === 'data' && <div className="rounded-xl border border-slate-200 bg-white p-5">{details('data')}</div>}
        {view === 'pipeline' && <div className="rounded-xl border border-slate-200 bg-white p-5">{details('pipeline')}</div>}
        {view === 'weather' && <WeatherEvidencePanel applicationId={application.id} claimDate={claimDate} webPanel={details('web')} />}
        {view === 'timeline' && <ChronologicalOverview application={application} fullWidth persona={application.persona} />}

        {/* Two columns from lg; below lg the cards interleave by importance (attention, steps, evidence…). */}
        {view === 'overview' && <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-start">
          <div className="contents lg:col-span-8 lg:block lg:space-y-4">
            <div className="order-1">
              <AttentionList
                signals={cockpit.signals}
                detectedCount={cockpit.detectedCount}
                analysisReady={!!data.aiSummary || !!fraudResult}
                density={density}
                onDensityChange={setDensity}
                onOpenEvidence={(signal: CaseSignal) => openTab(signal.tab)}
              />
            </div>
            <div className="order-3">
              <EvidenceStrip
                photos={cockpit.photos}
                documentCount={cockpit.documentCount}
                onOpenPhoto={setLightboxIndex}
                onOpenAll={() => openTab('evidence')}
              />
            </div>
          </div>
          <div className="contents lg:col-span-4 lg:block lg:space-y-4">
            <div className="order-2">
              <NextSteps
                steps={steps}
                checked={checked}
                onToggle={toggleStep}
                recommendedKey={recommendation?.taskKey}
                draftKeys={DRAFT_STEP_KEYS}
                onDraftMessage={() => openTab('customer')}
                settlement={cockpit.settlement}
                onGenerateSettlement={generateSettlement}
              />
            </div>
            <div className="order-4">
              <AuroraEvidenceSummary applicationId={application.id} onOpen={() => onChangeView('weather')} />
            </div>
            <div className="order-5">
              <LatestUpdates updates={cockpit.updates} previousVisit={previousVisit} onOpenTimeline={() => openTab('timeline')} />
            </div>
          </div>
        </div>}
      </div>

      <FraudAnalysisPanel
        applicationId={application.id}
        variant="headless"
        open={fraudOpen}
        onOpenChange={setFraudOpen}
        onFraudComplete={handleFraudComplete}
        onStatusChange={handleFraudStatus}
        savedResult={appFraud}
        startRequest={fraudStartRequest}
      />

      <DecisionDialog
        applicationId={application.id}
        open={decision.open}
        draft={decision.draft}
        riskLevel={fraudResult?.overall_assessment?.overall_fraud_risk}
        onClose={closeDecision}
        onSubmitted={refresh}
      />

      <AnalysisLaunchDialog
        open={launchOpen}
        loading={run.loading}
        error={run.error}
        canLaunch={data.files.length > 0}
        onClose={closeLaunch}
        onLaunch={launchAnalysis}
      />

      {lightboxIndex !== null && (
        <GalleryLightbox items={data.galleryItems} currentIndex={lightboxIndex} onClose={closeLightbox} onNavigate={setLightboxIndex} />
      )}
    </div>
  );
}

/** One cockpit per case: switching cases resets steps, drawer and dialogs. */
export default function PropertyCasualtyClaimsOverview(props: PropertyCasualtyClaimsOverviewProps) {
  return <PropertyCockpit key={props.application?.id ?? 'none'} {...props} />;
}
