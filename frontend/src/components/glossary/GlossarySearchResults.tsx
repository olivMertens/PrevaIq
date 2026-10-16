'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Edit2, Trash2 } from 'lucide-react';
import type { GlossaryTerm } from './useGlossaryManager';
import type { SortField, SortDir } from '../GlossaryManager';

interface GlossarySearchResultsProps {
  searchResults: GlossaryTerm[];
  searchQuery: string;
  saving: boolean;
  sortField: SortField;
  sortDir: SortDir;
  onClearSearch: () => void;
  onStartEditTerm: (term: GlossaryTerm) => void;
  onDeleteTerm: (abbreviation: string) => void;
}

export default function GlossarySearchResults({
  searchResults,
  searchQuery,
  saving,
  sortField,
  sortDir,
  onClearSearch,
  onStartEditTerm,
  onDeleteTerm,
}: GlossarySearchResultsProps) {
  const t = useTranslations('glossary');

  const sortedResults = useMemo(() => {
    const results = [...searchResults];
    results.sort((a, b) => {
      const aVal = (a[sortField] || '').toLowerCase();
      const bVal = (b[sortField] || '').toLowerCase();
      return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    });
    return results;
  }, [searchResults, sortField, sortDir]);

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium text-slate-700">
          {t('searchResults', { count: searchResults.length })}
        </h3>
        <button onClick={onClearSearch} className="text-sm text-slate-500 hover:text-slate-700">
          {t('clearSearch')}
        </button>
      </div>
      <div className="border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="px-4 py-2 text-left font-medium text-slate-600 w-32">{t('abbreviation')}</th>
              <th className="px-4 py-2 text-left font-medium text-slate-600">{t('meaning')}</th>
              <th className="px-4 py-2 text-left font-medium text-slate-600 w-40">{t('category')}</th>
              <th className="px-4 py-2 text-right font-medium text-slate-600 w-24">{t('actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sortedResults.map((term) => (
              <tr key={term.abbreviation} className="hover:bg-slate-50">
                <td className="px-4 py-2">
                  <span className="font-mono font-semibold text-slate-800">{term.abbreviation}</span>
                </td>
                <td className="px-4 py-2 text-slate-700">{term.meaning}</td>
                <td className="px-4 py-2 text-slate-500 text-sm">{term.category || '-'}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => onStartEditTerm(term)}
                    className="text-indigo-600 hover:text-indigo-800 p-1 mr-1" title={t('edit')}><Edit2 className="w-4 h-4" /></button>
                  <button onClick={() => onDeleteTerm(term.abbreviation)} disabled={saving}
                    className="text-red-500 hover:text-red-700 p-1" title={t('delete')}><Trash2 className="w-4 h-4" /></button>
                </td>
              </tr>
            ))}
            {searchResults.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                  {t('noSearchResults', { query: searchQuery })}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
