/**
 * Mortgage Workbench Component
 * 
 * Main 3-column layout for mortgage underwriting:
 * - Left: Evidence Panel (documents, extraction results)
 * - Center: Data + Policy Tabs (worksheet, calculations, policy checks, conditions)
 * - Right: Risk + Narrative Panel
 * 
 * Based on mortgage-research/underwriter_workbench_ux_spec.md
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Home, FileText, Calculator, Shield, AlertTriangle,
  RefreshCw, Sparkles, AlertCircle
} from 'lucide-react';
import EvidencePanel from './EvidencePanel';
import DataWorksheet from './DataWorksheet';
import CalculationsPanel from './CalculationsPanel';
import PolicyChecksPanel from './PolicyChecksPanel';
import RiskPanel from './RiskPanel';
import ConditionsPanel from './ConditionsPanel';
import DecisionBadge from './DecisionBadge';
import UnderwritingDecisionFooter from '@/components/UnderwritingDecisionFooter';
import PropertyDeepDiveModal from './PropertyDeepDiveModal';
import PDFViewer from '../claims/PDFViewer';
import { useToast } from '@/lib/ToastProvider';
import { useTranslations } from 'next-intl';
import type {
  MortgageApplication, MortgageDocument, MortgageFinding,
  MortgageBorrower, MortgageIncome, MortgageProperty,
  MortgageLoan, MortgageLiabilities, MortgageRatios,
  MortgageStressRatios, RiskSignal, FieldCitation,
} from './types';

// Re-export types for consumers that import from MortgageWorkbench
export type {
  MortgageBorrower, MortgageIncome, MortgageProperty,
  MortgageLoan, MortgageLiabilities, MortgageRatios,
  MortgageStressRatios, MortgageFinding, RiskSignal,
  FieldCitation, MortgageApplication, MortgageDocument,
} from './types';

interface MortgageWorkbenchProps {
  applicationId: string;
  isLoading?: boolean;
}

type CenterTab = 'data' | 'calculations' | 'policy' | 'conditions';

/**
 * Mortgage Workbench - Main Component
 */
export default function MortgageWorkbench({
  applicationId,
  isLoading = false,
}: MortgageWorkbenchProps) {
  const t = useTranslations('mortgageLabels');
  const [application, setApplication] = useState<MortgageApplication | null>(null);
  const [activeTab, setActiveTab] = useState<CenterTab>('data');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<MortgageDocument | null>(null);
  const [isPropertyDeepDiveOpen, setIsPropertyDeepDiveOpen] = useState(false);
  const { addToast } = useToast();

  // Handle document view click
  const handleViewDocument = (doc: MortgageDocument) => {
    if (doc.url) {
      setSelectedDocument(doc);
    }
  };

  // Fetch mortgage application data
  const fetchApplicationData = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    try {
      // Call the mortgage analyze endpoint
      const response = await fetch(`/api/mortgage/applications/${applicationId}`);
      if (!response.ok) {
        throw new Error('Failed to load application');
      }
      const data = await response.json();
      
      // Transform API response to component format
      const app: MortgageApplication = {
        application_id: data.id || applicationId,
        borrower: data.borrower || {
          name: 'Unknown',
          credit_score: 0,
        },
        income: {
          primary_borrower_income: data.income?.primary_borrower_income || 0,
          co_borrower_income: data.income?.co_borrower_income || 0,
          annual_salary: data.income?.annual_salary || data.income?.primary_borrower_income || 0,
          total_annual_income: data.income?.total_annual_income || 0,
          monthly_income: data.income?.monthly_income || 0,
        },
        property: data.property || {
          address: 'Unknown',
          purchase_price: 0,
          property_type: 'unknown',
        },
        loan: {
          amount: data.loan?.amount || 0,
          down_payment: data.loan?.down_payment || 0,
          down_payment_source: data.loan?.down_payment_source,
          amortization_years: data.loan?.amortization_years || 25,
          contract_rate: data.loan?.contract_rate || data.loan?.rate || 5.25,
          rate: data.loan?.contract_rate || data.loan?.rate || 5.25,
          qualifying_rate: data.loan?.qualifying_rate,
          term: data.loan?.term,
        },
        liabilities: data.liabilities || {
          property_taxes_monthly: 0,
          heating_monthly: 0,
        },
        ratios: data.ratios || {
          gds: 0,
          tds: 0,
          ltv: 0,
        },
        stress_ratios: data.stress_ratios || {
          gds: 0,
          tds: 0,
          qualifying_rate: 5.25,
        },
        decision: data.decision || 'REFER',
        findings: data.findings || [],
        risk_signals: data.risk_signals || [],
        documents: data.documents || [],
        narrative: data.narrative,
        policy_checks_count: data.policy_checks_count || 0,
        field_citations: data.field_citations || {},
      };
      
      setApplication(app);
    } catch (err) {
      console.error('Failed to fetch mortgage data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load mortgage data');
      addToast('error', t('loadError'));
    } finally {
      setIsRefreshing(false);
    }
  }, [applicationId]);

  useEffect(() => {
    fetchApplicationData();
  }, [fetchApplicationData]);

  const tabs: { id: CenterTab; label: string; icon: typeof Calculator }[] = [
    { id: 'data', label: t('tabData'), icon: FileText },
    { id: 'calculations', label: t('tabCalculations'), icon: Calculator },
    { id: 'policy', label: t('tabPolicyChecks'), icon: Shield },
    { id: 'conditions', label: t('tabConditions'), icon: AlertCircle },
  ];

  if (isLoading || isRefreshing) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-red-600">
        <AlertTriangle className="w-12 h-12 mb-4" />
        <p className="text-lg font-medium">{error}</p>
        <button
          onClick={fetchApplicationData}
          className="mt-4 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
        >
          {t('retry')}
        </button>
      </div>
    );
  }

  if (!application) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-slate-500">
        <Home className="w-12 h-12 mb-4" />
        <p className="text-lg">{t('noApplicationSelected')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Header Bar */}
      <div className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center">
              <Home className="w-5 h-5 text-emerald-600" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900">
                {application.borrower.name}
              </h1>
              <p className="text-sm text-slate-500">
                {t('caseRef')} {application.application_id} • {application.property.address}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <DecisionBadge decision={application.decision} />
            <button
              onClick={() => setIsPropertyDeepDiveOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-emerald-600 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors"
              title={t('propertyDeepDive')}
            >
              <Sparkles className="w-4 h-4" />
              {t('propertyDeepDive')}
            </button>
            <button
              onClick={fetchApplicationData}
              className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg"
              title={t('refresh')}
            >
              <RefreshCw className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Decision bar — sticky below header (same as claims) */}
      <UnderwritingDecisionFooter
        applicationId={applicationId}
        riskLevel={application.decision}
        hasBlockingFindings={application.findings?.some((f: MortgageFinding) => f.severity === 'fail')}
        position="top"
      />

      {/* Main 3-Column Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Column - Evidence Panel */}
        <div className="w-80 border-r border-slate-200 bg-white overflow-y-auto">
          <EvidencePanel
            documents={application.documents || []}
            borrower={application.borrower}
            property={application.property}
            onViewDocument={handleViewDocument}
          />
        </div>

        {/* Center Column - Tabs */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Tab Navigation */}
          <div className="bg-white border-b border-slate-200 px-4">
            <div className="flex gap-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.id
                      ? 'border-emerald-600 text-emerald-600'
                      : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
                  }`}
                >
                  <tab.icon className="w-4 h-4" />
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {activeTab === 'data' && (
              <DataWorksheet
                borrower={application.borrower}
                coBorrower={application.co_borrower}
                income={application.income}
                property={application.property}
                loan={application.loan}
                liabilities={application.liabilities}
                fieldCitations={application.field_citations}
              />
            )}
            {activeTab === 'calculations' && (
              <CalculationsPanel
                ratios={application.ratios}
                stressRatios={application.stress_ratios}
                loan={application.loan}
                income={application.income}
                liabilities={application.liabilities}
              />
            )}
            {activeTab === 'policy' && (
              <PolicyChecksPanel
                findings={application.findings}
                ratios={application.ratios}
                stressRatios={application.stress_ratios}
              />
            )}
            {activeTab === 'conditions' && (
              <ConditionsPanel findings={application.findings} />
            )}
          </div>
        </div>

        {/* Right Column - Risk & Narrative */}
        <div className="w-96 border-l border-slate-200 bg-white overflow-y-auto">
          <RiskPanel
            riskSignals={application.risk_signals}
            decision={application.decision}
            findings={application.findings}
            narrative={application.narrative}
            policyChecksCount={application.policy_checks_count}
          />
        </div>
      </div>

      {/* PDF Viewer Modal */}
      {selectedDocument && selectedDocument.url && (
        <PDFViewer
          url={selectedDocument.url}
          filename={selectedDocument.filename}
          onClose={() => setSelectedDocument(null)}
        />
      )}

      {/* Property Deep Dive Modal */}
      {isPropertyDeepDiveOpen && (
        <PropertyDeepDiveModal
          isOpen={isPropertyDeepDiveOpen}
          onClose={() => setIsPropertyDeepDiveOpen(false)}
          applicationId={applicationId}
          propertyAddress={application?.property?.address}
        />
      )}
    </div>
  );
}
