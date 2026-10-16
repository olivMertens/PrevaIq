'use client';

import { useState, useCallback, useEffect } from 'react';
import { getPrompts, updatePrompt, createPrompt, deletePrompt } from '@/lib/api';
import type { PromptsData } from '@/lib/types';
import { useToast } from '@/lib/ToastProvider';
import { useTranslations } from 'next-intl';

export function usePromptsManager(currentPersona: string, isActive: boolean) {
  const { addToast } = useToast();
  const t = useTranslations('adminPanel');
  const [promptsData, setPromptsData] = useState<PromptsData | null>(null);
  const [selectedSection, setSelectedSection] = useState('');
  const [selectedSubsection, setSelectedSubsection] = useState('');
  const [promptText, setPromptText] = useState('');
  const [promptsLoading, setPromptsLoading] = useState(false);
  const [promptsSaving, setPromptsSaving] = useState(false);
  const [promptsError, setPromptsError] = useState<string | null>(null);
  const [promptsSuccess, setPromptsSuccess] = useState<string | null>(null);

  // New prompt form state
  const [showNewPromptForm, setShowNewPromptForm] = useState(false);
  const [newSection, setNewSection] = useState('');
  const [newSubsection, setNewSubsection] = useState('');
  const [newPromptText, setNewPromptText] = useState('');

  const loadPrompts = useCallback(async (resetSelection = false) => {
    setPromptsLoading(true);
    setPromptsError(null);
    try {
      const data = await getPrompts(currentPersona);
      setPromptsData(data);

      if (resetSelection && data.prompts) {
        const sections = Object.keys(data.prompts);
        if (sections.length > 0) {
          const firstSection = sections[0];
          setSelectedSection(firstSection);
          const subsections = Object.keys(data.prompts[firstSection]);
          if (subsections.length > 0) {
            setSelectedSubsection(subsections[0]);
            setPromptText(data.prompts[firstSection][subsections[0]]);
          }
        } else {
          setSelectedSection('');
          setSelectedSubsection('');
          setPromptText('');
        }
      }
    } catch (err) {
      setPromptsError(err instanceof Error ? err.message : 'Failed to load prompts');
    } finally {
      setPromptsLoading(false);
    }
  }, [currentPersona]);

  // Load prompts when tab becomes active
  useEffect(() => {
    if (isActive && !promptsData && !promptsLoading) {
      loadPrompts(true);
    }
  }, [isActive, promptsData, promptsLoading, loadPrompts]);

  // Reload when persona changes
  useEffect(() => {
    if (isActive) {
      setPromptsData(null);
    }
  }, [currentPersona]); // eslint-disable-line react-hooks/exhaustive-deps

  // Update prompt text when selection changes
  useEffect(() => {
    if (promptsData && selectedSection && selectedSubsection) {
      const text = promptsData.prompts[selectedSection]?.[selectedSubsection] || '';
      setPromptText(text);
    }
  }, [promptsData, selectedSection, selectedSubsection]);

  const handleSavePrompt = useCallback(async () => {
    if (!selectedSection || !selectedSubsection) return;
    setPromptsSaving(true);
    setPromptsError(null);
    setPromptsSuccess(null);
    try {
      await updatePrompt(selectedSection, selectedSubsection, promptText, currentPersona);
      setPromptsSuccess(t('promptSaved'));
      addToast('success', t('promptSaved'));
      await loadPrompts(false);
      setTimeout(() => setPromptsSuccess(null), 3000);
    } catch (err) {
      setPromptsError(err instanceof Error ? err.message : t('failedToSavePrompt'));
    } finally {
      setPromptsSaving(false);
    }
  }, [selectedSection, selectedSubsection, promptText, currentPersona, loadPrompts]);

  const handleDeletePrompt = useCallback(async () => {
    if (!selectedSection || !selectedSubsection) return;
    if (!confirm(t('confirmResetPrompt', { section: selectedSection, subsection: selectedSubsection }))) return;
    setPromptsSaving(true);
    setPromptsError(null);
    try {
      await deletePrompt(selectedSection, selectedSubsection, currentPersona);
      setPromptsSuccess(t('promptReset'));
      await loadPrompts(true);
      setTimeout(() => setPromptsSuccess(null), 3000);
    } catch (err) {
      setPromptsError(err instanceof Error ? err.message : t('failedToResetPrompt'));
    } finally {
      setPromptsSaving(false);
    }
  }, [selectedSection, selectedSubsection, currentPersona, loadPrompts]);

  const handleCreatePrompt = useCallback(async () => {
    if (!newSection || !newSubsection || !newPromptText) {
      setPromptsError(t('fillAllFields'));
      return;
    }
    setPromptsSaving(true);
    setPromptsError(null);
    try {
      await createPrompt(newSection, newSubsection, newPromptText, currentPersona);
      setPromptsSuccess(t('promptCreated'));
      addToast('success', t('promptCreated'));
      setShowNewPromptForm(false);
      setNewSection('');
      setNewSubsection('');
      setNewPromptText('');
      await loadPrompts(true);
      setTimeout(() => setPromptsSuccess(null), 3000);
    } catch (err) {
      setPromptsError(err instanceof Error ? err.message : t('failedToCreatePrompt'));
    } finally {
      setPromptsSaving(false);
    }
  }, [newSection, newSubsection, newPromptText, currentPersona, loadPrompts]);

  return {
    promptsData,
    selectedSection,
    setSelectedSection,
    selectedSubsection,
    setSelectedSubsection,
    promptText,
    setPromptText,
    promptsLoading,
    promptsSaving,
    promptsError,
    promptsSuccess,
    showNewPromptForm,
    setShowNewPromptForm,
    newSection,
    setNewSection,
    newSubsection,
    setNewSubsection,
    newPromptText,
    setNewPromptText,
    handleSavePrompt,
    handleDeletePrompt,
    handleCreatePrompt,
  };
}
