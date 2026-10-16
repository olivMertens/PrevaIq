'use client';

import { useState } from 'react';
import Link from 'next/link';
import PersonaSelector from '@/components/PersonaSelector';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import GlossaryManager from '@/components/GlossaryManager';
import { useToast } from '@/lib/ToastProvider';
import { usePersona } from '@/lib/PersonaContext';
import { useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';
import { useDocumentProcessing } from '@/components/admin/useDocumentProcessing';
import { usePromptsManager } from '@/components/admin/usePromptsManager';
import { useAnalyzerManager } from '@/components/admin/useAnalyzerManager';
import { usePoliciesManager } from '@/components/admin/usePoliciesManager';
import DocumentsTab from '@/components/admin/DocumentsTab';
import PromptsTab from '@/components/admin/PromptsTab';
import AnalyzerTab from '@/components/admin/AnalyzerTab';
import PoliciesTab from '@/components/admin/PoliciesTab';
import CorrectionsTab from '@/components/admin/CorrectionsTab';
import AccessRequestsTab from '@/components/admin/AccessRequestsTab';
import BrandMark from '@/components/BrandMark';
import { useSessionRole } from '@/lib/useSessionRole';

type AdminTab = 'documents' | 'prompts' | 'policies' | 'analyzer' | 'glossary' | 'corrections' | 'access';

export default function AdminPage() {
  const { currentPersona, personaConfig } = usePersona();
  const t = useTranslations('adminPanel');
  const [activeTab, setActiveTab] = useState<AdminTab>('documents');

  const { addToast } = useToast();
  const role = useSessionRole();

  // Hooks for each tab
  const docs = useDocumentProcessing(currentPersona);
  const prompts = usePromptsManager(currentPersona, activeTab === 'prompts');
  const analyzer = useAnalyzerManager(currentPersona, activeTab === 'analyzer');
  const policies = usePoliciesManager(currentPersona, activeTab === 'policies');

  const tabs: { id: AdminTab; label: string }[] = [
    { id: 'documents', label: t('documentProcessing') },
    { id: 'prompts', label: t('agentSkills') },
    { id: 'policies', label: currentPersona.includes('claims') ? t('claimsPolicies') : t('underwritingPolicies') },
    { id: 'analyzer', label: t('analyzerManagement') },
    { id: 'glossary', label: t('glossaryTab') },
    { id: 'corrections', label: t('correctionsTab') },
    ...(role === 'admin' ? [{ id: 'access' as const, label: t('accessTab') }] : []),
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-slate-200">
        <div className="max-w-7xl 2xl:max-w-[96rem] mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2.5">
              <BrandMark compact />
            </Link>
            <span className="text-slate-300 font-light select-none">|</span>
            <h1 className="text-lg font-semibold text-slate-700">{t('title')}</h1>

            {/* Persona Selector — same position as portal */}
            <PersonaSelector />
          </div>
          <div className="flex items-center gap-4">
            <LanguageSwitcher />
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: brand.dotColor }}></div>
              <span className="text-sm text-slate-600">{t('backendConnected')}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Persona Banner */}
      <div
        className="border-b"
        style={{ backgroundColor: `${personaConfig.color}08`, borderColor: `${personaConfig.color}20` }}
      >
        <div className="max-w-7xl 2xl:max-w-[96rem] mx-auto px-4 py-3 flex items-center gap-3">
          <personaConfig.icon className="w-6 h-6" style={{ color: personaConfig.color }} />
          <div>
            <h2 className="font-medium text-slate-900">{personaConfig.name} — {t('workbench')}</h2>
            <p className="text-sm text-slate-600">{personaConfig.description}</p>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-7xl 2xl:max-w-[96rem] mx-auto px-4">
          <nav className="flex space-x-8">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === tab.id
                    ? ''
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                }`}
                style={activeTab === tab.id ? { color: brand.primary, borderColor: brand.primary } : undefined}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </div>

      <main className="max-w-7xl 2xl:max-w-[96rem] mx-auto px-4 py-8">
        {activeTab === 'documents' && (
          <DocumentsTab
            applications={docs.applications}
            loading={docs.loading}
            error={docs.error}
            processing={docs.processing}
            isProcessing={docs.isProcessing}
            currentPersona={currentPersona}
            onUploadAndProcess={docs.handleUploadAndProcess}
            onReprocess={docs.handleReprocess}
            onDeleteApp={docs.handleDeleteApp}
            onRefresh={docs.loadApplications}
            onPollResume={docs.pollForProcessingCompletion}
            onDismissProcessing={() => docs.setProcessing({ step: 'idle', message: '' })}
            addToast={addToast}
          />
        )}

        {activeTab === 'prompts' && (
          <PromptsTab
            promptsData={prompts.promptsData}
            selectedSection={prompts.selectedSection}
            setSelectedSection={prompts.setSelectedSection}
            selectedSubsection={prompts.selectedSubsection}
            setSelectedSubsection={prompts.setSelectedSubsection}
            promptText={prompts.promptText}
            setPromptText={prompts.setPromptText}
            promptsLoading={prompts.promptsLoading}
            promptsSaving={prompts.promptsSaving}
            promptsError={prompts.promptsError}
            promptsSuccess={prompts.promptsSuccess}
            showNewPromptForm={prompts.showNewPromptForm}
            setShowNewPromptForm={prompts.setShowNewPromptForm}
            newSection={prompts.newSection}
            setNewSection={prompts.setNewSection}
            newSubsection={prompts.newSubsection}
            setNewSubsection={prompts.setNewSubsection}
            newPromptText={prompts.newPromptText}
            setNewPromptText={prompts.setNewPromptText}
            onSavePrompt={prompts.handleSavePrompt}
            onDeletePrompt={prompts.handleDeletePrompt}
            onCreatePrompt={prompts.handleCreatePrompt}
          />
        )}

        {activeTab === 'policies' && (
          <PoliciesTab
            policies={policies.policies}
            policiesLoading={policies.policiesLoading}
            policiesSaving={policies.policiesSaving}
            policiesError={policies.policiesError}
            policiesSuccess={policies.policiesSuccess}
            selectedPolicy={policies.selectedPolicy}
            showNewPolicyForm={policies.showNewPolicyForm}
            indexStats={policies.indexStats}
            reindexing={policies.reindexing}
            isClaimsPersona={policies.isClaimsPersona}
            isAutomotiveClaimsPersona={policies.isAutomotiveClaimsPersona}
            policyFormData={policies.policyFormData}
            setPolicyFormData={policies.setPolicyFormData}
            claimsPolicyFormData={policies.claimsPolicyFormData}
            setClaimsPolicyFormData={policies.setClaimsPolicyFormData}
            onSelectPolicy={policies.handleSelectPolicy}
            onNewPolicyClick={policies.handleNewPolicyClick}
            onSavePolicy={policies.handleSavePolicy}
            onDeletePolicy={policies.handleDeletePolicy}
            onReindexPolicies={policies.handleReindexPolicies}
            onAddCriteria={policies.handleAddCriteria}
            onRemoveCriteria={policies.handleRemoveCriteria}
            onCriteriaChange={policies.handleCriteriaChange}
            onCancel={() => {
              policies.setSelectedPolicy(null);
              policies.setShowNewPolicyForm(false);
            }}
          />
        )}

        {activeTab === 'analyzer' && (
          <AnalyzerTab
            analyzerStatus={analyzer.analyzerStatus}
            analyzerSchema={analyzer.analyzerSchema}
            analyzers={analyzer.analyzers}
            analyzerLoading={analyzer.analyzerLoading}
            analyzerProcessing={analyzer.analyzerProcessing}
            analyzerError={analyzer.analyzerError}
            analyzerSuccess={analyzer.analyzerSuccess}
            onCreateAnalyzer={analyzer.handleCreateAnalyzer}
            onDeleteAnalyzer={analyzer.handleDeleteAnalyzer}
          />
        )}

        {activeTab === 'glossary' && (
          <GlossaryManager persona={currentPersona} personaName={personaConfig.name} />
        )}

        {activeTab === 'corrections' && (
          <CorrectionsTab currentPersona={currentPersona} />
        )}

        {activeTab === 'access' && role === 'admin' && <AccessRequestsTab />}
      </main>
    </div>
  );
}
