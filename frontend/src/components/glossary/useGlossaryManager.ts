'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  getGlossary,
  searchGlossary,
  createGlossaryTerm,
  updateGlossaryTerm,
  deleteGlossaryTerm,
  createGlossaryCategory,
  updateGlossaryCategory,
  deleteGlossaryCategory,
} from '@/lib/api';
import type { PersonaGlossary, GlossaryCategory, GlossaryTerm } from '@/lib/api';
import { useToast } from '@/lib/ToastProvider';
import { useTranslations } from 'next-intl';

export type { PersonaGlossary, GlossaryCategory, GlossaryTerm };

export default function useGlossaryManager(persona: string) {
  const { addToast } = useToast();
  const t = useTranslations('glossaryManager');
  const [glossary, setGlossary] = useState<PersonaGlossary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<GlossaryTerm[] | null>(null);
  const [searching, setSearching] = useState(false);

  // Expanded categories
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());

  // Edit state
  const [editingTerm, setEditingTerm] = useState<string | null>(null);
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [editFormData, setEditFormData] = useState<Partial<GlossaryTerm>>({});
  const [editCategoryName, setEditCategoryName] = useState('');

  // New term form
  const [showNewTermForm, setShowNewTermForm] = useState<string | null>(null);
  const [newTermData, setNewTermData] = useState<Partial<GlossaryTerm>>({
    abbreviation: '',
    meaning: '',
    context: '',
  });

  // New category form
  const [showNewCategoryForm, setShowNewCategoryForm] = useState(false);
  const [newCategoryData, setNewCategoryData] = useState({ id: '', name: '' });

  // Alphabetic filter
  const [letterFilter, setLetterFilter] = useState<string | null>(null);

  const loadGlossary = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getGlossary(persona);
      setGlossary(data);
      if (data.categories.length > 0) {
        setExpandedCategories(new Set([data.categories[0].id]));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [persona, t]);

  useEffect(() => {
    loadGlossary();
  }, [loadGlossary]);

  // Search handling
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }

    const timeoutId = setTimeout(async () => {
      try {
        setSearching(true);
        const result = await searchGlossary(persona, searchQuery);
        setSearchResults(result.results);
      } catch (err) {
        console.error('Search failed:', err);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [searchQuery, persona]);

  const filteredCategories = useMemo(() => {
    if (!glossary) return [];
    if (!letterFilter) return glossary.categories;

    return glossary.categories.map(cat => ({
      ...cat,
      terms: cat.terms.filter(term =>
        term.abbreviation.toUpperCase().startsWith(letterFilter)
      ),
    })).filter(cat => cat.terms.length > 0);
  }, [glossary, letterFilter]);

  const availableLetters = useMemo(() => {
    if (!glossary) return [];
    const letters = new Set<string>();
    glossary.categories.forEach(cat => {
      cat.terms.forEach(term => {
        const firstChar = term.abbreviation.charAt(0).toUpperCase();
        if (/[A-Z]/.test(firstChar)) {
          letters.add(firstChar);
        }
      });
    });
    return Array.from(letters).sort();
  }, [glossary]);

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories(prev => {
      const newSet = new Set(prev);
      if (newSet.has(categoryId)) newSet.delete(categoryId);
      else newSet.add(categoryId);
      return newSet;
    });
  };

  const showMessage = (message: string, isError: boolean = false) => {
    if (isError) {
      setError(message);
      addToast('error', message);
      setTimeout(() => setError(null), 5000);
    } else {
      setSuccess(message);
      addToast('success', message);
      setTimeout(() => setSuccess(null), 3000);
    }
  };

  const handleAddTerm = async (categoryId: string) => {
    if (!newTermData.abbreviation || !newTermData.meaning) {
      showMessage(t('termFieldsRequired'), true);
      return;
    }
    try {
      setSaving(true);
      await createGlossaryTerm(persona, categoryId, {
        abbreviation: newTermData.abbreviation,
        meaning: newTermData.meaning,
        context: newTermData.context || undefined,
      });
      showMessage(t('termAdded', { abbreviation: newTermData.abbreviation || '' }));
      setShowNewTermForm(null);
      setNewTermData({ abbreviation: '', meaning: '', context: '' });
      await loadGlossary();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : t('termAddFailed'), true);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateTerm = async (abbreviation: string) => {
    if (!editFormData.meaning) {
      showMessage(t('meaningRequired'), true);
      return;
    }
    try {
      setSaving(true);
      await updateGlossaryTerm(persona, abbreviation, {
        meaning: editFormData.meaning,
        context: editFormData.context || undefined,
      });
      showMessage(t('termUpdated', { abbreviation }));
      setEditingTerm(null);
      setEditFormData({});
      await loadGlossary();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : t('termUpdateFailed'), true);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteTerm = async (abbreviation: string) => {
    if (!confirm(t('deleteTermConfirm', { abbreviation }))) return;
    try {
      setSaving(true);
      await deleteGlossaryTerm(persona, abbreviation);
      showMessage(t('termDeleted', { abbreviation }));
      await loadGlossary();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : t('termDeleteFailed'), true);
    } finally {
      setSaving(false);
    }
  };

  const handleAddCategory = async () => {
    if (!newCategoryData.id || !newCategoryData.name) {
      showMessage(t('categoryFieldsRequired'), true);
      return;
    }
    try {
      setSaving(true);
      await createGlossaryCategory(persona, newCategoryData.id, newCategoryData.name);
      showMessage(t('categoryAdded', { name: newCategoryData.name }));
      setShowNewCategoryForm(false);
      setNewCategoryData({ id: '', name: '' });
      await loadGlossary();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : t('categoryAddFailed'), true);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateCategory = async (categoryId: string) => {
    if (!editCategoryName) {
      showMessage(t('categoryNameRequired'), true);
      return;
    }
    try {
      setSaving(true);
      await updateGlossaryCategory(persona, categoryId, editCategoryName);
      showMessage(t('categoryUpdated', { name: editCategoryName }));
      setEditingCategory(null);
      setEditCategoryName('');
      await loadGlossary();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : t('categoryUpdateFailed'), true);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCategory = async (categoryId: string, termCount: number) => {
    if (termCount > 0) {
      showMessage(t('categoryNotEmpty'), true);
      return;
    }
    if (!confirm(t('deleteCategoryConfirm', { id: categoryId }))) return;
    try {
      setSaving(true);
      await deleteGlossaryCategory(persona, categoryId);
      showMessage(t('categoryDeleted'));
      await loadGlossary();
    } catch (err) {
      showMessage(err instanceof Error ? err.message : t('categoryDeleteFailed'), true);
    } finally {
      setSaving(false);
    }
  };

  const startEditingTerm = (term: GlossaryTerm) => {
    setEditingTerm(term.abbreviation);
    setEditFormData({ meaning: term.meaning, context: term.context || '' });
  };

  return {
    // Data
    glossary,
    loading,
    error,
    success,
    saving,
    searchQuery,
    searchResults,
    searching,
    expandedCategories,
    editingTerm,
    editingCategory,
    editFormData,
    editCategoryName,
    showNewTermForm,
    newTermData,
    showNewCategoryForm,
    newCategoryData,
    letterFilter,
    filteredCategories,
    availableLetters,
    // Setters
    setSearchQuery,
    setSearchResults,
    setEditingTerm,
    setEditingCategory,
    setEditFormData,
    setEditCategoryName,
    setShowNewTermForm,
    setNewTermData,
    setShowNewCategoryForm,
    setNewCategoryData,
    setLetterFilter,
    // Actions
    toggleCategory,
    startEditingTerm,
    handleAddTerm,
    handleUpdateTerm,
    handleDeleteTerm,
    handleAddCategory,
    handleUpdateCategory,
    handleDeleteCategory,
    setExpandedCategories,
  };
}
