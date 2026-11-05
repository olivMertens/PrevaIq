'use client';

import type { FraudAnalysisResponse } from '@/lib/api';
import { applicationCurrency } from '@/lib/currency';
import type { ApplicationMetadata } from '@/lib/types';
import type { DeepDiveTab } from '@/components/case/caseSignals';
import { PipelineDetails } from '@/components/case/PipelineStatusPill';
import CoverTab from './CoverTab';
import CustomerTab from './CustomerTab';
import DataTab from './DataTab';
import EvidenceTab from './EvidenceTab';
import FraudTab from './FraudTab';
import SummaryTab from './SummaryTab';
import TimelineTab from './TimelineTab';
import WebCheckTab from './WebCheckTab';
import { getFieldValue, parseAiSummary } from './propertyClaimHelpers';
import type { usePropertyClaimData } from './usePropertyClaimData';

export const DEEP_DIVE_TABS: DeepDiveTab[] = [
  'summary', 'fraud', 'web', 'cover', 'evidence', 'customer', 'timeline', 'data', 'pipeline',
];

interface PropertyDeepDiveProps {
  tab: DeepDiveTab;
  application: ApplicationMetadata;
  data: ReturnType<typeof usePropertyClaimData>;
  fraud: FraudAnalysisResponse | null;
  fraudStatus: { isLoading: boolean; progress: number };
  analyzing: boolean;
  estimatedAmount: number;
  decisionStatus: 'approved' | 'pending';
  upload: { uploading: boolean; progressMessage: string | null; addFiles: (files: FileList | null) => void };
  onRelaunch: () => void;
  onOpenFraudReport: () => void;
  onOpenFile: (index: number) => void;
  onRefresh: () => void;
}

/** Content of the deep-dive drawer: the full detail behind each cockpit fact. */
export default function PropertyDeepDive({
  tab,
  application,
  data,
  fraud,
  fraudStatus,
  analyzing,
  estimatedAmount,
  decisionStatus,
  upload,
  onRelaunch,
  onOpenFraudReport,
  onOpenFile,
  onRefresh,
}: PropertyDeepDiveProps) {
  const { ef, aiSummary } = data;
  const field = (...keys: string[]) => getFieldValue(ef, keys, '');

  switch (tab) {
    case 'summary':
      return (
        <SummaryTab
          application={application}
          aiSummary={aiSummary}
          damages={[
            ...data.injuries.map((item) => ({ label: item.diagnosis, related: item.related })),
            ...data.markdownDerivedDamages.map((item) => ({ label: item.description, related: item.related })),
          ]}
          analyzing={analyzing}
          onRelaunch={onRelaunch}
        />
      );
    case 'fraud':
      return <FraudTab result={fraud} running={fraudStatus.isLoading} progress={fraudStatus.progress} onOpenReport={onOpenFraudReport} />;
    case 'web':
      return <WebCheckTab web={fraud?.web_intelligence} />;
    case 'cover':
      return (
        <CoverTab
          labels={application.context_labels ?? []}
          llmOutputs={data.llmOutputs}
          currency={applicationCurrency(application)}
          claimedText={field('MontantEstime', 'TotalIncurred', 'MontantTotal')}
          deductibleText={field('FranchiseApplicable', 'Franchise') || undefined}
          coverageText={parseAiSummary(aiSummary || '').decision}
        />
      );
    case 'evidence':
      return (
        <EvidenceTab
          items={data.evidenceItems}
          imageAnalyses={fraud?.image_analyses ?? []}
          uploading={upload.uploading}
          progressMessage={upload.progressMessage}
          onAddFiles={upload.addFiles}
          onOpen={onOpenFile}
        />
      );
    case 'customer':
      return (
        <CustomerTab
          application={application}
          customerData={data.customerData}
          linkedCustomerId={application.external_reference}
          claimNature={field('NatureSinistre', 'CauseOfLoss')}
          estimatedAmount={estimatedAmount}
          insuredName={field('InsuredName', 'NomAssure', 'NomSouscripteur')}
          claimReference={field('ClaimNumber', 'NumeroSinistre', 'ReferenceDossier') || application.external_reference || application.id}
          settlementAmount={field('SettlementAmount', 'MontantIndemnisation', 'IndemniteRecommandee', 'MontantEstime')}
          decisionStatus={decisionStatus}
          suggestedAddress={field('AdresseAssure', 'LieuSinistre')}
          suggestedPhone={field('TelephoneAssure')}
          suggestedEmail={field('EmailAssure')}
          onAffiliated={onRefresh}
        />
      );
    case 'timeline':
      return <TimelineTab events={data.liabilityEvents} />;
    case 'data':
      return (
        <DataTab
          extractedFields={ef}
          derivedFields={data.markdownDerivedFields}
          persona={application.persona || 'habitation_claims'}
        />
      );
    case 'pipeline':
      return <PipelineDetails application={application} />;
    default:
      return null;
  }
}
