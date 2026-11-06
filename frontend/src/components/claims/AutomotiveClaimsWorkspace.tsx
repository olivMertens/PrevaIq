'use client';

import { useCallback, useState } from 'react';
import { Globe, HeartHandshake, ShieldCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ApplicationMetadata } from '@/lib/types';
import type { CaseView } from '@/lib/caseUrl';
import { getApplication, type FraudAnalysisResponse } from '@/lib/api';
import { claimCommunicationStatus, claimViewForDetail, savedClaimFraud } from '@/lib/claimsWorkspace';
import { useToast } from '@/lib/ToastProvider';
import type { DeepDiveTab } from '@/components/case/caseSignals';
import ClaimAnalysisSections from '@/components/case/ClaimAnalysisSections';
import LocationCard from '@/components/case/LocationCard';
import ChronologicalOverview from '@/components/ChronologicalOverview';
import DocumentsPanel from '@/components/DocumentsPanel';
import AutomotiveClaimsOverview from './AutomotiveClaimsOverview';
import FraudAnalysisPanel from './FraudAnalysisPanel';
import PropertyDeepDive from './property/PropertyDeepDive';
import AnalysisLaunchDialog from './property/AnalysisLaunchDialog';
import { usePropertyClaimData } from './property/usePropertyClaimData';
import { useAnalysisRun } from './property/useAnalysisRun';
import { useFileUpload } from './property/useFileUpload';
import { getFieldValue, parseAmount } from './property/propertyClaimHelpers';

export default function AutomotiveClaimsWorkspace({
  application,
  view,
  onChangeView,
  onApplicationUpdate,
}: {
  application: ApplicationMetadata;
  view: CaseView;
  onChangeView: (view: CaseView) => void;
  onApplicationUpdate: (application: ApplicationMetadata) => void;
}) {
  const t = useTranslations('caseCockpit');
  const { addToast } = useToast();
  const data = usePropertyClaimData(application);
  const run = useAnalysisRun(application, onApplicationUpdate, false);
  const upload = useFileUpload(application, onApplicationUpdate);
  const [focus, setFocus] = useState<DeepDiveTab>('summary');
  const [result, setResult] = useState<FraudAnalysisResponse | null>(null);
  const [fraudOpen, setFraudOpen] = useState(false);
  const [startRequest, setStartRequest] = useState(0);
  const [launchOpen, setLaunchOpen] = useState(false);
  const [status, setStatus] = useState<{ isLoading: boolean; progress: number; error: string | null }>({ isLoading: false, progress: 0, error: null });
  const saved = savedClaimFraud(application);
  const fraud = result ?? saved;
  const applicationId = application.id;
  const refresh = useCallback(() => {
    getApplication(applicationId).then(onApplicationUpdate).catch(() => addToast('error', t('workspace.refreshError')));
  }, [applicationId, onApplicationUpdate, addToast, t]);
  const complete = useCallback((next: FraudAnalysisResponse) => {
    setResult(next);
    refresh();
  }, [refresh]);
  const open = (tab: DeepDiveTab) => {
    setFocus(tab);
    onChangeView(claimViewForDetail(tab));
  };
  const start = () => { if (!status.isLoading) setStartRequest((current) => current + 1); };
  const details = (tab: DeepDiveTab) => (
    <PropertyDeepDive tab={tab} application={application} data={data} fraud={fraud}
      fraudStatus={status} analyzing={run.analyzing} estimatedAmount={parseAmount(getFieldValue(data.ef, ['MontantEstime', 'TotalIncurred']))}
      decisionStatus={claimCommunicationStatus(application)} upload={upload} onRelaunch={() => setLaunchOpen(true)}
      onOpenFraudReport={() => setFraudOpen(true)} onRunFraud={start} onRefresh={refresh}
      onOpenFile={() => onChangeView('documents')} />
  );
  const controls = (
    <div className="flex flex-wrap gap-2">
      <button type="button" disabled={status.isLoading} onClick={fraud ? () => open('fraud') : start}
        className="inline-flex items-center gap-2 rounded-lg border border-purple-200 bg-purple-50 px-3 py-2 text-sm font-medium text-purple-900 disabled:opacity-50">
        <ShieldCheck className="h-4 w-4" aria-hidden />
        {status.isLoading ? t('kpi.analyzing', { progress: status.progress }) : fraud ? t('fraudTab.openReport') : t('fraudTab.run')}
      </button>
      <button type="button" onClick={() => open('web')} className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-900">
        <Globe className="h-4 w-4" aria-hidden />{t('drawer.tabs.web')}
      </button>
      <button type="button" onClick={() => open('customer')} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800">
        <HeartHandshake className="h-4 w-4" aria-hidden />{t('workspace.prepareReply')}
      </button>
    </div>
  );
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {status.error && <p role="alert" className="bg-rose-50 p-3 text-sm text-rose-900">{status.error}</p>}
      <div className={view === 'overview' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}>
        <AutomotiveClaimsOverview key={`${application.id}-${application.analysis_language ?? ''}`} applicationId={application.id} analysisControls={controls} />
      </div>
      {view !== 'overview' && view !== 'source' && (
        <div className="min-h-0 flex-1 overflow-y-auto bg-slate-100 p-4 pb-24">
          <div className="mx-auto max-w-[1600px] space-y-4">
            {status.isLoading && <p role="status" className="text-sm text-purple-900">{t('kpi.analyzing', { progress: status.progress })}</p>}
            {view === 'analysis' && <ClaimAnalysisSections focus={focus} facts={<details className="rounded-xl border bg-white p-4"><summary className="cursor-pointer font-semibold">{t('facts.title')}</summary>{details('data')}</details>} renderSection={details} />}
            {view === 'documents' && <DocumentsPanel files={application.files || []} applicationId={application.id} />}
            {view === 'customer' && <div className="rounded-xl border bg-white p-5">{details('customer')}</div>}
            {view === 'weather' && <LocationCard applicationId={application.id} claimDate={getFieldValue(data.ef, ['DateSinistre', 'ClaimDate'])} />}
            {view === 'timeline' && <ChronologicalOverview application={application} persona="automotive_claims" fullWidth />}
            {view === 'data' && details('data')}
            {view === 'pipeline' && details('pipeline')}
          </div>
        </div>
      )}
      <FraudAnalysisPanel applicationId={application.id} variant="headless" open={fraudOpen} onOpenChange={setFraudOpen}
        savedResult={saved} startRequest={startRequest} onFraudComplete={complete} onStatusChange={setStatus} />
      <AnalysisLaunchDialog open={launchOpen} loading={run.loading} error={run.error} canLaunch={data.files.length > 0}
        onClose={() => setLaunchOpen(false)} onLaunch={async () => { if (await run.launch()) setLaunchOpen(false); }} />
      {run.error && !launchOpen && <p role="alert" className="bg-rose-50 p-3 text-sm text-rose-900">{run.error}</p>}
    </div>
  );
}
