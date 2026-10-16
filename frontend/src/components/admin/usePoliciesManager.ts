'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  getPolicies,
  createPolicy as createPolicyApi,
  updatePolicy as updatePolicyApi,
  deletePolicy as deletePolicyApi,
  reindexAllPolicies,
  getIndexStats,
} from '@/lib/api';
import type { UnderwritingPolicy, PolicyCriteriaItem } from '@/lib/types';
import type { IndexStats } from '@/lib/api';
import { useToast } from '@/lib/ToastProvider';
import { useTranslations } from 'next-intl';

export function usePoliciesManager(currentPersona: string, isActive: boolean) {
  const { addToast } = useToast();
  const t = useTranslations('adminPanel');
  const [policies, setPolicies] = useState<UnderwritingPolicy[]>([]);
  const [policiesLoading, setPoliciesLoading] = useState(false);
  const [policiesSaving, setPoliciesSaving] = useState(false);
  const [policiesError, setPoliciesError] = useState<string | null>(null);
  const [policiesSuccess, setPoliciesSuccess] = useState<string | null>(null);
  const [selectedPolicy, setSelectedPolicy] = useState<UnderwritingPolicy | null>(null);
  const [showNewPolicyForm, setShowNewPolicyForm] = useState(false);
  const [indexStats, setIndexStats] = useState<IndexStats | null>(null);
  const [reindexing, setReindexing] = useState(false);

  const isClaimsPersona = currentPersona.includes('claims');
  const isAutomotiveClaimsPersona = currentPersona === 'automotive_claims';

  // Underwriting policy form
  const [policyFormData, setPolicyFormData] = useState({
    id: '',
    category: '',
    subcategory: '',
    name: '',
    description: '',
    criteria: [] as PolicyCriteriaItem[],
    references: [] as string[],
  });

  // Claims policy form (different structure)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [claimsPolicyFormData, setClaimsPolicyFormData] = useState<Record<string, any>>({});

  const loadPolicies = useCallback(async () => {
    setPoliciesLoading(true);
    setPoliciesError(null);
    try {
      const data = await getPolicies(currentPersona);
      setPolicies(data.policies);
    } catch (err) {
      setPoliciesError(err instanceof Error ? err.message : 'Failed to load policies');
    } finally {
      setPoliciesLoading(false);
    }
  }, [currentPersona]);

  const loadIndexStats = useCallback(async () => {
    try {
      const stats = await getIndexStats(currentPersona);
      setIndexStats(stats);
    } catch {
      setIndexStats(null);
    }
  }, [currentPersona]);

  // Load when tab becomes active
  useEffect(() => {
    if (isActive && policies.length === 0 && !policiesLoading) {
      loadPolicies();
      loadIndexStats();
    }
  }, [isActive, policies.length, policiesLoading, loadPolicies, loadIndexStats]);

  // Reload when persona changes
  useEffect(() => {
    if (isActive) {
      setPolicies([]);
    }
  }, [currentPersona]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelectPolicy = useCallback((policy: UnderwritingPolicy) => {
    setSelectedPolicy(policy);
    if (isClaimsPersona) {
      setClaimsPolicyFormData({ ...policy });
    } else {
      setPolicyFormData({
        id: policy.id,
        category: policy.category,
        subcategory: policy.subcategory,
        name: policy.name,
        description: policy.description,
        criteria: policy.criteria || [],
        references: policy.references || [],
      });
    }
    setShowNewPolicyForm(false);
  }, [isClaimsPersona]);

  const handleNewPolicyClick = useCallback(() => {
    setSelectedPolicy(null);
    if (isClaimsPersona) {
      setClaimsPolicyFormData({
        id: '',
        plan_name: '',
        plan_type: 'HMO',
        network: '',
        deductible: { individual: '', family: '' },
        oop_max: { individual: '', family: '' },
        copays: { pcp_visit: '', specialist_visit: '', urgent_care: '', er_visit: '' },
        coinsurance: '',
        preventive_care: 'Covered 100%',
        exclusions: [],
      });
    } else {
      setPolicyFormData({
        id: '',
        category: '',
        subcategory: '',
        name: '',
        description: '',
        criteria: [],
        references: [],
      });
    }
    setShowNewPolicyForm(true);
  }, [isClaimsPersona]);

  const handleSavePolicy = useCallback(async () => {
    setPoliciesSaving(true);
    setPoliciesError(null);
    setPoliciesSuccess(null);
    try {
      if (showNewPolicyForm) {
        await createPolicyApi(policyFormData);
        setPoliciesSuccess(t('policySaved'));
        addToast('success', t('policySaved'));
        setShowNewPolicyForm(false);
      } else if (selectedPolicy) {
        const { id, ...updateData } = policyFormData;
        await updatePolicyApi(selectedPolicy.id, updateData);
        setPoliciesSuccess(t('policyUpdated'));
        addToast('success', t('policyUpdated'));
      }
      await loadPolicies();
      setTimeout(() => setPoliciesSuccess(null), 3000);
    } catch (err) {
      setPoliciesError(err instanceof Error ? err.message : t('failedToSavePolicy'));
    } finally {
      setPoliciesSaving(false);
    }
  }, [showNewPolicyForm, selectedPolicy, policyFormData, loadPolicies]);

  const handleDeletePolicy = useCallback(async () => {
    if (!selectedPolicy) return;
    if (!confirm(t('confirmDeletePolicy', { name: selectedPolicy.name }))) return;
    setPoliciesSaving(true);
    setPoliciesError(null);
    try {
      await deletePolicyApi(selectedPolicy.id);
      setPoliciesSuccess(t('policyDeleted'));
      addToast('info', t('policyDeleted'));
      setSelectedPolicy(null);
      await loadPolicies();
      setTimeout(() => setPoliciesSuccess(null), 3000);
    } catch (err) {
      setPoliciesError(err instanceof Error ? err.message : t('failedToSavePolicy'));
    } finally {
      setPoliciesSaving(false);
    }
  }, [selectedPolicy, loadPolicies]);

  const handleReindexPolicies = useCallback(async () => {
    const policyType = isClaimsPersona ? 'claims' : 'underwriting';
    if (!confirm(t('confirmReindex', { type: policyType }))) return;
    setReindexing(true);
    setPoliciesError(null);
    try {
      const result = await reindexAllPolicies(true, currentPersona);
      if (result.status === 'success') {
        setPoliciesSuccess(
          t('reindexComplete', { policiesIndexed: result.policies_indexed ?? 0, chunksStored: result.chunks_stored ?? 0, totalTime: result.total_time_seconds ?? 0 })
        );
        const stats = await getIndexStats(currentPersona);
        setIndexStats(stats);
      } else if (result.status === 'skipped') {
        setPoliciesError(result.error || t('reindexSkipped'));
      } else {
        setPoliciesError(result.error || t('failedToReindexPolicies'));
      }
      setTimeout(() => setPoliciesSuccess(null), 5000);
    } catch (err) {
      setPoliciesError(err instanceof Error ? err.message : t('failedToReindexPolicies'));
    } finally {
      setReindexing(false);
    }
  }, [isClaimsPersona, currentPersona]);

  const handleAddCriteria = useCallback(() => {
    setPolicyFormData(prev => ({
      ...prev,
      criteria: [
        ...prev.criteria,
        { id: `${prev.id}-${prev.criteria.length + 1}`, condition: '', risk_level: 'Low', action: '', rationale: '' }
      ]
    }));
  }, []);

  const handleRemoveCriteria = useCallback((index: number) => {
    setPolicyFormData(prev => ({
      ...prev,
      criteria: prev.criteria.filter((_, i) => i !== index)
    }));
  }, []);

  const handleCriteriaChange = useCallback((index: number, field: keyof PolicyCriteriaItem, value: string) => {
    setPolicyFormData(prev => ({
      ...prev,
      criteria: prev.criteria.map((c, i) => i === index ? { ...c, [field]: value } : c)
    }));
  }, []);

  return {
    policies,
    policiesLoading,
    policiesSaving,
    policiesError,
    policiesSuccess,
    selectedPolicy,
    setSelectedPolicy,
    showNewPolicyForm,
    setShowNewPolicyForm,
    indexStats,
    reindexing,
    isClaimsPersona,
    isAutomotiveClaimsPersona,
    policyFormData,
    setPolicyFormData,
    claimsPolicyFormData,
    setClaimsPolicyFormData,
    handleSelectPolicy,
    handleNewPolicyClick,
    handleSavePolicy,
    handleDeletePolicy,
    handleReindexPolicies,
    handleAddCriteria,
    handleRemoveCriteria,
    handleCriteriaChange,
  };
}
