'use client';

import {
  RefreshCw,
  Plus,
  Trash2,
  Loader2,
  FileText,
  AlertCircle,
  Check,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { UnderwritingPolicy, PolicyCriteriaItem, IndexStats } from './types';

interface PoliciesTabProps {
  policies: UnderwritingPolicy[];
  policiesLoading: boolean;
  policiesSaving: boolean;
  policiesError: string | null;
  policiesSuccess: string | null;
  selectedPolicy: UnderwritingPolicy | null;
  showNewPolicyForm: boolean;
  indexStats: IndexStats | null;
  reindexing: boolean;
  isClaimsPersona: boolean;
  isAutomotiveClaimsPersona: boolean;
  policyFormData: {
    id: string;
    category: string;
    subcategory: string;
    name: string;
    description: string;
    criteria: PolicyCriteriaItem[];
    references: string[];
  };
  setPolicyFormData: React.Dispatch<React.SetStateAction<PoliciesTabProps['policyFormData']>>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  claimsPolicyFormData: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setClaimsPolicyFormData: React.Dispatch<React.SetStateAction<Record<string, any>>>;
  onSelectPolicy: (policy: UnderwritingPolicy) => void;
  onNewPolicyClick: () => void;
  onSavePolicy: () => void;
  onDeletePolicy: () => void;
  onReindexPolicies: () => void;
  onAddCriteria: () => void;
  onRemoveCriteria: (index: number) => void;
  onCriteriaChange: (index: number, field: keyof PolicyCriteriaItem, value: string) => void;
  onCancel: () => void;
}

export default function PoliciesTab({
  policies,
  policiesLoading,
  policiesSaving,
  policiesError,
  policiesSuccess,
  selectedPolicy,
  showNewPolicyForm,
  indexStats,
  reindexing,
  isClaimsPersona,
  isAutomotiveClaimsPersona,
  policyFormData,
  setPolicyFormData,
  claimsPolicyFormData,
  setClaimsPolicyFormData,
  onSelectPolicy,
  onNewPolicyClick,
  onSavePolicy,
  onDeletePolicy,
  onReindexPolicies,
  onAddCriteria,
  onRemoveCriteria,
  onCriteriaChange,
  onCancel,
}: PoliciesTabProps) {
  const t = useTranslations('adminPanel');
  const tp = useTranslations('adminLabels');

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Policy List */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-900">
              {isClaimsPersona ? t('claimsPolicies') : t('underwritingPolicies')}
            </h2>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={onReindexPolicies} disabled={reindexing}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium border border-slate-300 text-slate-700 bg-white rounded-lg hover:bg-slate-50 hover:border-slate-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title={t('reindexPolicies')}>
              <RefreshCw className={`w-4 h-4 ${reindexing ? 'animate-spin' : ''}`} />
              {reindexing ? t('indexing') : t('reindex')}
            </button>
            <button onClick={onNewPolicyClick}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
              <Plus className="w-4 h-4" /> {t('newPolicy')}
            </button>
          </div>
        </div>

        {indexStats && indexStats.status === 'ok' && (
          <div className="px-5 py-3 bg-emerald-50 border-b border-emerald-100 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
            <span className="text-xs font-medium text-emerald-800">
              RAG Index: {indexStats.total_chunks || indexStats.chunk_count || 0} {t('chunksFrom')} {indexStats.policy_count} {t('policies')}
            </span>
          </div>
        )}

        <div className="p-3">
          {policiesLoading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 text-indigo-600 animate-spin" /></div>
          ) : policies.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <p className="text-sm text-slate-500">{t('noPoliciesFound')}</p>
              <p className="text-xs text-slate-400 mt-1">{t('createFirstPolicy')}</p>
            </div>
          ) : (
            <div className="space-y-1.5 max-h-[550px] overflow-y-auto">
              {policies.map((policy) => (
                <button key={policy.id} onClick={() => onSelectPolicy(policy)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all ${
                    selectedPolicy?.id === policy.id ? 'border-indigo-500 bg-indigo-50 shadow-sm' : 'border-transparent hover:border-slate-200 hover:bg-slate-50'
                  }`}>
                  <div className="font-medium text-slate-900 text-sm">{policy.name || policy.id}</div>
                  {isAutomotiveClaimsPersona ? (
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    <div className="text-xs text-slate-500 mt-0.5">{(policy as any).category || 'damage_assessment'} • {(policy as any).subcategory || 'general'}</div>
                  ) : isClaimsPersona ? (
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    <div className="text-xs text-slate-500 mt-0.5">{(policy as any).plan_type} • {(policy as any).network?.split(' ')[0] || 'N/A'}</div>
                  ) : (
                    <div className="text-xs text-slate-500 mt-0.5">{policy.category} / {policy.subcategory}</div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Policy Editor */}
      <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        {policiesError && (
          <div className="mx-5 mt-5 p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" /> {policiesError}
          </div>
        )}
        {policiesSuccess && (
          <div className="mx-5 mt-5 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-700 text-sm flex items-center gap-2">
            <Check className="w-4 h-4 flex-shrink-0" /> {policiesSuccess}
          </div>
        )}

        {(selectedPolicy || showNewPolicyForm) ? (
          <div>
            <div className="px-5 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-900">
                {showNewPolicyForm ? t('createNewPolicy') : `${t('editPolicy')} ${selectedPolicy?.name || selectedPolicy?.id}`}
              </h2>
              {selectedPolicy && !showNewPolicyForm && (
                <button onClick={onDeletePolicy}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-rose-600 hover:text-rose-700 hover:bg-rose-50 rounded-lg transition-colors">
                  <Trash2 className="w-4 h-4" /> {t('delete')}
                </button>
              )}
            </div>

            <div className="p-5 space-y-5">
              {isAutomotiveClaimsPersona ? (
                <AutomotivePolicyEditor formData={claimsPolicyFormData} setFormData={setClaimsPolicyFormData} showNewPolicyForm={showNewPolicyForm} t={t} />
              ) : isClaimsPersona ? (
                <HealthPolicyEditor formData={claimsPolicyFormData} setFormData={setClaimsPolicyFormData} showNewPolicyForm={showNewPolicyForm} t={t} />
              ) : (
                <UnderwritingPolicyEditor formData={policyFormData} setPolicyFormData={setPolicyFormData}
                  showNewPolicyForm={showNewPolicyForm} onAddCriteria={onAddCriteria} onRemoveCriteria={onRemoveCriteria} onCriteriaChange={onCriteriaChange} t={t} />
              )}

              <div className="flex justify-end gap-3 pt-5 border-t border-slate-200">
                <button onClick={onCancel} className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">{t('cancel')}</button>
                <button onClick={onSavePolicy} disabled={policiesSaving}
                  className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                  {policiesSaving ? t('saving') : showNewPolicyForm ? t('createPolicy') : t('saveChanges')}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-slate-500">
            <FileText className="w-12 h-12 text-slate-300 mb-4" />
            <p className="text-base font-medium mb-1">{t('selectPolicyToEdit')}</p>
            <p className="text-sm text-slate-400">{t('orCreateNew')}</p>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Automotive Policy Editor ───────────────────── */
function AutomotivePolicyEditor({ formData, setFormData, showNewPolicyForm, t }: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  formData: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setFormData: React.Dispatch<React.SetStateAction<Record<string, any>>>;
  showNewPolicyForm: boolean;
  t: (key: string) => string;
}) {
  const tp = useTranslations('adminLabels');
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('policyId')}</label>
          <input type="text" value={formData.id || ''} onChange={(e) => setFormData(prev => ({ ...prev, id: e.target.value }))}
            disabled={!showNewPolicyForm} className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm disabled:bg-slate-100 font-mono" placeholder={tp('policyId')} />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('policyName')}</label>
          <input type="text" value={formData.name || ''} onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" placeholder={tp('policyName')} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('category')}</label>
          <select value={formData.category || 'damage_assessment'} onChange={(e) => setFormData(prev => ({ ...prev, category: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm">
            {['damage_assessment', 'coverage', 'liability', 'fraud_detection', 'payout_rules', 'repair_requirements', 'documentation', 'total_loss'].map(cat => (
              <option key={cat} value={cat}>{cat.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('subcategory')}</label>
          <input type="text" value={formData.subcategory || ''} onChange={(e) => setFormData(prev => ({ ...prev, subcategory: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" placeholder={tp('policyField')} />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">{t('descriptionLabel')}</label>
        <textarea value={formData.description || ''} onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-20" placeholder={tp('policyDescription')} />
      </div>

      {/* Criteria */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-slate-700">{t('policyCriteria')}</label>
          <button type="button" onClick={() => {
            const newCriteria = [...(formData.criteria || []), { id: `C${(formData.criteria?.length || 0) + 1}`, condition: '', severity: 'moderate', action: '', rationale: '' }];
            setFormData(prev => ({ ...prev, criteria: newCriteria }));
          }} className="text-xs text-indigo-600 hover:text-indigo-700 font-medium">{t('addCriterion')}</button>
        </div>
        <div className="space-y-3">
          {(formData.criteria || []).map((criterion: { id: string; condition: string; severity: string; action: string; rationale: string }, idx: number) => (
            <div key={idx} className="p-3 bg-slate-50 rounded-lg border border-slate-200 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500">{t('criterion')} {idx + 1}</span>
                <button type="button" onClick={() => {
                  const c = [...formData.criteria]; c.splice(idx, 1); setFormData(prev => ({ ...prev, criteria: c }));
                }} className="text-xs text-rose-500 hover:text-rose-600">{t('remove')}</button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <input type="text" value={criterion.id || ''} onChange={(e) => {
                  const c = [...formData.criteria]; c[idx] = { ...criterion, id: e.target.value }; setFormData(prev => ({ ...prev, criteria: c }));
                }} className="px-2 py-1.5 border border-slate-300 rounded text-xs" placeholder={t('idExample')} />
                <select value={criterion.severity || 'moderate'} onChange={(e) => {
                  const c = [...formData.criteria]; c[idx] = { ...criterion, severity: e.target.value }; setFormData(prev => ({ ...prev, criteria: c }));
                }} className="px-2 py-1.5 border border-slate-300 rounded text-xs">
                  {['minor', 'moderate', 'major', 'severe', 'total_loss'].map(s => <option key={s} value={s}>{t(s)}</option>)}
                </select>
              </div>
              <input type="text" value={criterion.condition || ''} onChange={(e) => {
                const c = [...formData.criteria]; c[idx] = { ...criterion, condition: e.target.value }; setFormData(prev => ({ ...prev, criteria: c }));
              }} className="w-full px-2 py-1.5 border border-slate-300 rounded text-xs" placeholder={t('conditionPlaceholder')} />
              <input type="text" value={criterion.action || ''} onChange={(e) => {
                const c = [...formData.criteria]; c[idx] = { ...criterion, action: e.target.value }; setFormData(prev => ({ ...prev, criteria: c }));
              }} className="w-full px-2 py-1.5 border border-slate-300 rounded text-xs" placeholder={t('actionPlaceholder')} />
              <input type="text" value={criterion.rationale || ''} onChange={(e) => {
                const c = [...formData.criteria]; c[idx] = { ...criterion, rationale: e.target.value }; setFormData(prev => ({ ...prev, criteria: c }));
              }} className="w-full px-2 py-1.5 border border-slate-300 rounded text-xs" placeholder={t('rationalePlaceholder')} />
            </div>
          ))}
          {(!formData.criteria || formData.criteria.length === 0) && <p className="text-xs text-slate-400 italic">{t('noCriteriaDefined')}</p>}
        </div>
      </div>

      {/* Modifying Factors */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-slate-700">{t('modifyingFactors')}</label>
          <button type="button" onClick={() => {
            const f = [...(formData.modifying_factors || []), { factor: '', impact: '' }];
            setFormData(prev => ({ ...prev, modifying_factors: f }));
          }} className="text-xs text-indigo-600 hover:text-indigo-700 font-medium">{t('addFactor')}</button>
        </div>
        <div className="space-y-2">
          {(formData.modifying_factors || []).map((factor: { factor: string; impact: string }, idx: number) => (
            <div key={idx} className="flex gap-2 items-start">
              <input type="text" value={factor.factor || ''} onChange={(e) => {
                const f = [...formData.modifying_factors]; f[idx] = { ...factor, factor: e.target.value }; setFormData(prev => ({ ...prev, modifying_factors: f }));
              }} className="flex-1 px-2 py-1.5 border border-slate-300 rounded text-xs" placeholder={t('factorName')} />
              <input type="text" value={factor.impact || ''} onChange={(e) => {
                const f = [...formData.modifying_factors]; f[idx] = { ...factor, impact: e.target.value }; setFormData(prev => ({ ...prev, modifying_factors: f }));
              }} className="flex-1 px-2 py-1.5 border border-slate-300 rounded text-xs" placeholder={t('impactDescription')} />
              <button type="button" onClick={() => {
                const f = [...formData.modifying_factors]; f.splice(idx, 1); setFormData(prev => ({ ...prev, modifying_factors: f }));
              }} className="text-rose-500 hover:text-rose-600 p-1"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
          ))}
          {(!formData.modifying_factors || formData.modifying_factors.length === 0) && <p className="text-xs text-slate-400 italic">{t('noModifyingFactors')}</p>}
        </div>
      </div>

      {/* References */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">{t('references')}</label>
        <textarea value={Array.isArray(formData.references) ? formData.references.join('\n') : ''}
          onChange={(e) => setFormData(prev => ({ ...prev, references: e.target.value.split('\n').filter(Boolean) }))}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-20"
          placeholder={"One reference per line:\nNHTSA Guidelines Section 4.2\nInsurance Code 1234"} />
      </div>
    </div>
  );
}

/* ── Health Claims Policy Editor ───────────────────── */
function HealthPolicyEditor({ formData, setFormData, showNewPolicyForm, t }: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  formData: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setFormData: React.Dispatch<React.SetStateAction<Record<string, any>>>;
  showNewPolicyForm: boolean;
  t: (key: string) => string;
}) {
  const tp = useTranslations('adminLabels');
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('planName')}</label>
          <input type="text" value={formData.plan_name || formData.name || ''}
            onChange={(e) => setFormData(prev => ({ ...prev, plan_name: e.target.value, name: e.target.value }))}
            disabled={!showNewPolicyForm} className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm disabled:bg-slate-100" placeholder={tp('policyPlanName')} />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('planType')}</label>
          <select value={formData.plan_type || 'HMO'} onChange={(e) => setFormData(prev => ({ ...prev, plan_type: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm">
            {['HMO', 'PPO', 'EPO', 'POS'].map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">{t('network')}</label>
        <input type="text" value={formData.network || ''} onChange={(e) => setFormData(prev => ({ ...prev, network: e.target.value }))}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" placeholder={tp('policyNetwork')} />
      </div>

      {/* Deductible */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-2">{t('deductible')}</label>
        <div className="grid grid-cols-2 gap-4">
          {(['individual', 'family'] as const).map(key => (
            <div key={key}>
              <label className="block text-xs text-slate-500 mb-1">{t(key)}</label>
              <input type="text" value={formData.deductible?.[key] || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, deductible: { ...prev.deductible, [key]: e.target.value } }))}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" placeholder={tp('policyDeductible')} />
            </div>
          ))}
        </div>
      </div>

      {/* OOP Max */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-2">{t('outOfPocketMax')}</label>
        <div className="grid grid-cols-2 gap-4">
          {(['individual', 'family'] as const).map(key => (
            <div key={key}>
              <label className="block text-xs text-slate-500 mb-1">{t(key)}</label>
              <input type="text" value={formData.oop_max?.[key] || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, oop_max: { ...prev.oop_max, [key]: e.target.value } }))}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" placeholder={tp('policyOopMax')} />
            </div>
          ))}
        </div>
      </div>

      {/* Copays */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-2">{t('copays')}</label>
        <div className="grid grid-cols-2 gap-3">
          {([
            ['pcp_visit', 'pcpVisit', '$20'],
            ['specialist_visit', 'specialistVisit', '$40'],
            ['urgent_care', 'urgentCare', '$50'],
            ['er_visit', 'erVisit', '$250'],
          ] as const).map(([field, labelKey, placeholder]) => (
            <div key={field}>
              <label className="block text-xs text-slate-500 mb-1">{t(labelKey)}</label>
              <input type="text" value={formData.copays?.[field] || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, copays: { ...prev.copays, [field]: e.target.value } }))}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" placeholder={placeholder} />
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('coinsurance')}</label>
          <input type="text" value={formData.coinsurance || ''} onChange={(e) => setFormData(prev => ({ ...prev, coinsurance: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" placeholder={tp('policyCoinsurance')} />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">{t('preventiveCare')}</label>
          <input type="text" value={formData.preventive_care || ''} onChange={(e) => setFormData(prev => ({ ...prev, preventive_care: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" placeholder={tp('policyCoverage')} />
        </div>
      </div>

      {/* Exclusions */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">{t('exclusions')}</label>
        <textarea value={Array.isArray(formData.exclusions) ? formData.exclusions.join('\n') : ''}
          onChange={(e) => setFormData(prev => ({ ...prev, exclusions: e.target.value.split('\n').filter(Boolean) }))}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-20" placeholder={t('exclusionsPlaceholder')} />
      </div>
    </div>
  );
}

/* ── Underwriting Policy Editor ───────────────────── */
function UnderwritingPolicyEditor({ formData, setPolicyFormData, showNewPolicyForm, onAddCriteria, onRemoveCriteria, onCriteriaChange, t }: {
  formData: PoliciesTabProps['policyFormData'];
  setPolicyFormData: React.Dispatch<React.SetStateAction<PoliciesTabProps['policyFormData']>>;
  showNewPolicyForm: boolean;
  onAddCriteria: () => void;
  onRemoveCriteria: (index: number) => void;
  onCriteriaChange: (index: number, field: keyof PolicyCriteriaItem, value: string) => void;
  t: (key: string) => string;
}) {
  return (
    <>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">{t('policyId')}</label>
          <input type="text" value={formData.id} onChange={(e) => setPolicyFormData(prev => ({ ...prev, id: e.target.value }))}
            disabled={!showNewPolicyForm} className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono disabled:bg-slate-50 disabled:text-slate-500 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors" placeholder={t('placeholderCvdId')} />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">{t('name')}</label>
          <input type="text" value={formData.name} onChange={(e) => setPolicyFormData(prev => ({ ...prev, name: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors" placeholder={t('placeholderPolicyName')} />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">{t('category')}</label>
          <input type="text" value={formData.category} onChange={(e) => setPolicyFormData(prev => ({ ...prev, category: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors" placeholder={t('placeholderCategory')} />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">{t('subcategory')}</label>
          <input type="text" value={formData.subcategory} onChange={(e) => setPolicyFormData(prev => ({ ...prev, subcategory: e.target.value }))}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors" placeholder={t('placeholderCondition')} />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1.5">{t('descriptionLabel')}</label>
        <textarea value={formData.description} onChange={(e) => setPolicyFormData(prev => ({ ...prev, description: e.target.value }))}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-24 resize-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors" placeholder={t('placeholderDescription')} />
      </div>

      {/* Criteria */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <label className="block text-sm font-medium text-slate-700">{t('criteria')}</label>
          <button type="button" onClick={onAddCriteria}
            className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors">
            <Plus className="w-4 h-4" /> {t('addCriteria')}
          </button>
        </div>
        <div className="space-y-3 max-h-[350px] overflow-y-auto pr-1">
          {formData.criteria.map((criteria, index) => (
            <div key={index} className="p-4 border border-slate-200 rounded-lg bg-slate-50/50">
              <div className="flex justify-between items-start mb-3">
                <span className="text-xs font-mono text-indigo-600 bg-indigo-50 px-2 py-1 rounded">{criteria.id}</span>
                <button type="button" onClick={() => onRemoveCriteria(index)}
                  className="inline-flex items-center gap-1 text-rose-500 hover:text-rose-700 text-xs font-medium transition-colors">{t('remove')}</button>
              </div>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <input type="text" value={criteria.condition} onChange={(e) => onCriteriaChange(index, 'condition', e.target.value)}
                  className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors" placeholder={t('placeholderConditionCriteria')} />
                <select value={criteria.risk_level} onChange={(e) => onCriteriaChange(index, 'risk_level', e.target.value)}
                  className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors bg-white">
                  {['Low', 'Low-Moderate', 'Moderate', 'Moderate-High', 'High'].map(l => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
              <input type="text" value={criteria.action} onChange={(e) => onCriteriaChange(index, 'action', e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm mb-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors" placeholder={t('placeholderAction')} />
              <textarea value={criteria.rationale} onChange={(e) => onCriteriaChange(index, 'rationale', e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-16 resize-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors" placeholder={t('placeholderRationale')} />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
