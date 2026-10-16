'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Plus,
  Trash2,
  Edit2,
  Save,
  X,
  ChevronDown,
  ChevronRight,
  Check,
} from 'lucide-react';
import type { GlossaryCategory, GlossaryTerm } from './useGlossaryManager';
import type { SortField, SortDir } from '../GlossaryManager';

interface GlossaryCategorySectionProps {
  category: GlossaryCategory;
  isExpanded: boolean;
  editingTerm: string | null;
  editingCategory: string | null;
  editFormData: Partial<GlossaryTerm>;
  editCategoryName: string;
  showNewTermForm: string | null;
  newTermData: Partial<GlossaryTerm>;
  saving: boolean;
  sortField: SortField;
  sortDir: SortDir;
  onToggle: (id: string) => void;
  onStartEditTerm: (term: GlossaryTerm) => void;
  onCancelEditTerm: () => void;
  onUpdateTerm: (abbreviation: string) => void;
  onDeleteTerm: (abbreviation: string) => void;
  onShowNewTermForm: (categoryId: string) => void;
  onCancelNewTerm: () => void;
  onNewTermChange: (data: Partial<GlossaryTerm>) => void;
  onAddTerm: (categoryId: string) => void;
  onStartEditCategory: (id: string, name: string) => void;
  onCancelEditCategory: () => void;
  onEditCategoryNameChange: (name: string) => void;
  onUpdateCategory: (id: string) => void;
  onDeleteCategory: (id: string, termCount: number) => void;
  onEditFormDataChange: (data: Partial<GlossaryTerm>) => void;
  onExpandCategory: (id: string) => void;
}

export default function GlossaryCategorySection({
  category,
  isExpanded,
  editingTerm,
  editingCategory,
  editFormData,
  editCategoryName,
  showNewTermForm,
  newTermData,
  saving,
  sortField,
  sortDir,
  onToggle,
  onStartEditTerm,
  onCancelEditTerm,
  onUpdateTerm,
  onDeleteTerm,
  onShowNewTermForm,
  onCancelNewTerm,
  onNewTermChange,
  onAddTerm,
  onStartEditCategory,
  onCancelEditCategory,
  onEditCategoryNameChange,
  onUpdateCategory,
  onDeleteCategory,
  onEditFormDataChange,
  onExpandCategory,
}: GlossaryCategorySectionProps) {
  const t = useTranslations('glossary');
  const isEditingCat = editingCategory === category.id;

  const sortedTerms = useMemo(() => {
    const terms = [...category.terms];
    terms.sort((a, b) => {
      const aVal = (a[sortField] || '').toLowerCase();
      const bVal = (b[sortField] || '').toLowerCase();
      return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    });
    return terms;
  }, [category.terms, sortField, sortDir]);

  const renderTermRow = (term: GlossaryTerm) => {
    const isEditing = editingTerm === term.abbreviation;

    if (isEditing) {
      return (
        <tr key={term.abbreviation} className="bg-indigo-50">
          <td className="px-4 py-2">
            <span className="font-mono font-semibold text-indigo-700">{term.abbreviation}</span>
          </td>
          <td className="px-4 py-2">
            <input type="text" value={editFormData.meaning || ''}
              onChange={(e) => onEditFormDataChange({ ...editFormData, meaning: e.target.value })}
              className="w-full px-2 py-1 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder={t('meaning')} />
          </td>
          <td className="px-4 py-2">
            <input type="text" value={editFormData.context || ''}
              onChange={(e) => onEditFormDataChange({ ...editFormData, context: e.target.value })}
              className="w-full px-2 py-1 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder={t('contextOptional')} />
          </td>
          <td className="px-4 py-2 text-right">
            <button onClick={() => onUpdateTerm(term.abbreviation)} disabled={saving}
              className="text-green-600 hover:text-green-800 p-1 mr-1" title={t('save')}><Save className="w-4 h-4" /></button>
            <button onClick={onCancelEditTerm} className="text-slate-500 hover:text-slate-700 p-1" title={t('cancel')}><X className="w-4 h-4" /></button>
          </td>
        </tr>
      );
    }

    return (
      <tr key={term.abbreviation} className="hover:bg-slate-50">
        <td className="px-4 py-2"><span className="font-mono font-semibold text-slate-800">{term.abbreviation}</span></td>
        <td className="px-4 py-2 text-slate-700">{term.meaning}</td>
        <td className="px-4 py-2 text-slate-500 text-sm">{term.context || '-'}</td>
        <td className="px-4 py-2 text-right">
          <button onClick={() => onStartEditTerm(term)} className="text-indigo-600 hover:text-indigo-800 p-1 mr-1" title={t('edit')}><Edit2 className="w-4 h-4" /></button>
          <button onClick={() => onDeleteTerm(term.abbreviation)} disabled={saving}
            className="text-red-500 hover:text-red-700 p-1" title={t('delete')}><Trash2 className="w-4 h-4" /></button>
        </td>
      </tr>
    );
  };

  const renderNewTermForm = () => {
    if (showNewTermForm !== category.id) return null;
    return (
      <tr className="bg-green-50">
        <td className="px-4 py-2">
          <input type="text" value={newTermData.abbreviation || ''}
            onChange={(e) => onNewTermChange({ ...newTermData, abbreviation: e.target.value })}
            className="w-full px-2 py-1 border border-slate-300 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder={t('abbreviation')} autoFocus />
        </td>
        <td className="px-4 py-2">
          <input type="text" value={newTermData.meaning || ''}
            onChange={(e) => onNewTermChange({ ...newTermData, meaning: e.target.value })}
            className="w-full px-2 py-1 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder={t('meaning')} />
        </td>
        <td className="px-4 py-2">
          <input type="text" value={newTermData.context || ''}
            onChange={(e) => onNewTermChange({ ...newTermData, context: e.target.value })}
            className="w-full px-2 py-1 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder={t('contextOptional')} />
        </td>
        <td className="px-4 py-2 text-right">
          <button onClick={() => onAddTerm(category.id)} disabled={saving}
            className="text-green-600 hover:text-green-800 p-1 mr-1" title={t('add')}><Check className="w-4 h-4" /></button>
          <button onClick={onCancelNewTerm} className="text-slate-500 hover:text-slate-700 p-1" title={t('cancel')}><X className="w-4 h-4" /></button>
        </td>
      </tr>
    );
  };

  return (
    <div className="border border-slate-200 rounded-lg mb-4 overflow-hidden">
      {/* Category header */}
      <div className="bg-slate-100 px-4 py-3 flex items-center justify-between">
        <button onClick={() => onToggle(category.id)}
          className="flex items-center gap-2 font-medium text-slate-800 hover:text-indigo-600">
          {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          {isEditingCat ? (
            <input type="text" value={editCategoryName}
              onChange={(e) => onEditCategoryNameChange(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              className="px-2 py-1 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              autoFocus />
          ) : (
            <span>{category.name}</span>
          )}
          <span className="text-sm font-normal text-slate-500">({category.terms.length} {t('terms')})</span>
        </button>

        <div className="flex items-center gap-2">
          {isEditingCat ? (
            <>
              <button onClick={() => onUpdateCategory(category.id)} disabled={saving}
                className="text-green-600 hover:text-green-800 p-1" title={t('save')}><Save className="w-4 h-4" /></button>
              <button onClick={onCancelEditCategory}
                className="text-slate-500 hover:text-slate-700 p-1" title={t('cancel')}><X className="w-4 h-4" /></button>
            </>
          ) : (
            <>
              <button onClick={() => { onShowNewTermForm(category.id); onExpandCategory(category.id); }}
                className="text-green-600 hover:text-green-800 p-1" title={t('addTerm')}><Plus className="w-4 h-4" /></button>
              <button onClick={() => onStartEditCategory(category.id, category.name)}
                className="text-indigo-600 hover:text-indigo-800 p-1" title={t('editCategory')}><Edit2 className="w-4 h-4" /></button>
              <button onClick={() => onDeleteCategory(category.id, category.terms.length)}
                disabled={saving || category.terms.length > 0}
                className={`p-1 ${category.terms.length > 0 ? 'text-slate-300 cursor-not-allowed' : 'text-red-500 hover:text-red-700'}`}
                title={category.terms.length > 0 ? t('deleteCategoryFirst') : t('deleteCategory')}>
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Category terms table */}
      {isExpanded && (
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="px-4 py-2 text-left font-medium text-slate-600 w-32">{t('abbreviation')}</th>
              <th className="px-4 py-2 text-left font-medium text-slate-600">{t('meaning')}</th>
              <th className="px-4 py-2 text-left font-medium text-slate-600 w-48">{t('context')}</th>
              <th className="px-4 py-2 text-right font-medium text-slate-600 w-24">{t('actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {renderNewTermForm()}
            {sortedTerms.map((term) => renderTermRow(term))}
            {category.terms.length === 0 && showNewTermForm !== category.id && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                  {t('noTermsInCategory')}{' '}
                  <button onClick={() => onShowNewTermForm(category.id)} className="text-indigo-600 hover:underline">{t('addFirstTerm')}</button>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
