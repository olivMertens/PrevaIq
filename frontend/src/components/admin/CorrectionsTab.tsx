'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Loader2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  Database,
  Zap,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { fetchCorrections, fetchCorrectionStats } from '@/lib/api';
import type { Correction, CorrectionStats } from '@/lib/api';

interface CorrectionsTabProps {
  currentPersona: string;
}

export default function CorrectionsTab({ currentPersona }: CorrectionsTabProps) {
  const t = useTranslations('corrections');

  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [stats, setStats] = useState<CorrectionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [filterPersona, setFilterPersona] = useState<string>('');
  const [filterAgent, setFilterAgent] = useState<string>('');
  const [filterCategory, setFilterCategory] = useState<string>('');

  // Expanded row
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [correctionsRes, statsRes] = await Promise.all([
        fetchCorrections({
          persona: filterPersona || undefined,
          agent_type: filterAgent || undefined,
          category: filterCategory || undefined,
          limit: 200,
        }),
        fetchCorrectionStats(),
      ]);
      setCorrections(correctionsRes.corrections);
      setStats(statsRes);
    } catch (e) {
      setError(t('loadError'));
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filterPersona, filterAgent, filterCategory, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Derive unique values for filter dropdowns
  const uniquePersonas = [...new Set(corrections.map(c => c.persona))].sort();
  const uniqueAgents = [...new Set(corrections.map(c => c.agent_type))].sort();
  const uniqueCategories = [...new Set(corrections.map(c => c.metadata?.category).filter(Boolean))].sort();

  const riskLevelColor = (level?: string) => {
    switch (level) {
      case 'faible': return 'bg-green-100 text-green-800';
      case 'modere': return 'bg-yellow-100 text-yellow-800';
      case 'eleve': return 'bg-orange-100 text-orange-800';
      case 'tres_eleve': return 'bg-red-100 text-red-800';
      default: return 'bg-slate-100 text-slate-600';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">{t('title')}</h2>
          <p className="text-sm text-slate-500 mt-1">{t('description')}</p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          title={t('refresh')}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="flex items-center gap-2 text-slate-500 text-sm">
              <Database className="w-4 h-4" />
              {t('totalCorrections')}
            </div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{stats.total}</div>
          </div>
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="flex items-center gap-2 text-emerald-600 text-sm">
              <CheckCircle2 className="w-4 h-4" />
              {t('activeCorrections')}
            </div>
            <div className="text-2xl font-bold text-emerald-700 mt-1">{stats.active}</div>
          </div>
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="flex items-center gap-2 text-indigo-600 text-sm">
              <Zap className="w-4 h-4" />
              {t('withEmbedding')}
            </div>
            <div className="text-2xl font-bold text-indigo-700 mt-1">{stats.with_embedding}</div>
          </div>
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="flex items-center gap-2 text-slate-500 text-sm">
              {t('categories')}
            </div>
            <div className="text-2xl font-bold text-slate-900 mt-1">
              {stats.by_category ? Object.keys(stats.by_category).length : 0}
            </div>
          </div>
        </div>
      )}

      {/* Category breakdown */}
      {stats?.by_category && Object.keys(stats.by_category).length > 0 && (
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h3 className="text-sm font-medium text-slate-700 mb-3">{t('categories')}</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.by_category).map(([cat, count]) => (
              <button
                key={cat}
                onClick={() => setFilterCategory(filterCategory === cat ? '' : cat)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  filterCategory === cat
                    ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-300'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {cat} ({count})
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4">
        <select
          value={filterPersona}
          onChange={e => setFilterPersona(e.target.value)}
          title={t('filterPersona')}
          className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
        >
          <option value="">{t('allPersonas')}</option>
          {uniquePersonas.map(p => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <select
          value={filterAgent}
          onChange={e => setFilterAgent(e.target.value)}
          title={t('filterAgent')}
          className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
        >
          <option value="">{t('allAgents')}</option>
          {uniqueAgents.map(a => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          value={filterCategory}
          onChange={e => setFilterCategory(e.target.value)}
          title={t('filterCategory')}
          className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
        >
          <option value="">{t('allCategories')}</option>
          {uniqueCategories.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 rounded-lg text-red-700">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      )}

      {/* Table */}
      {!loading && corrections.length === 0 && (
        <div className="text-center py-12 text-slate-500">{t('noCorrections')}</div>
      )}

      {!loading && corrections.length > 0 && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-slate-600 w-8"></th>
                <th className="text-left px-4 py-3 font-medium text-slate-600">ID</th>
                <th className="text-left px-4 py-3 font-medium text-slate-600">{t('query')}</th>
                <th className="text-left px-4 py-3 font-medium text-slate-600">{t('riskLevel')}</th>
                <th className="text-left px-4 py-3 font-medium text-slate-600">{t('policyRef')}</th>
                <th className="text-left px-4 py-3 font-medium text-slate-600">{t('correctedBy')}</th>
                <th className="text-left px-4 py-3 font-medium text-slate-600">{t('embeddingStatus')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {corrections.map(c => (
                <>
                  <tr
                    key={c.example_id}
                    className="hover:bg-slate-50 cursor-pointer transition-colors"
                    onClick={() => setExpandedId(expandedId === c.example_id ? null : c.example_id)}
                  >
                    <td className="px-4 py-3">
                      {expandedId === c.example_id
                        ? <ChevronUp className="w-4 h-4 text-slate-400" />
                        : <ChevronDown className="w-4 h-4 text-slate-400" />}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {c.metadata?.source_id || c.example_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3 max-w-xs truncate" title={c.query}>
                      {c.query.length > 80 ? c.query.slice(0, 80) + '...' : c.query}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${riskLevelColor(c.metadata?.risk_level)}`}>
                        {c.metadata?.risk_level || '-'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">{c.metadata?.policy_ref || '-'}</td>
                    <td className="px-4 py-3 text-xs text-slate-600">{c.metadata?.corrected_by || '-'}</td>
                    <td className="px-4 py-3">
                      {c.has_embedding
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        : <XCircle className="w-4 h-4 text-slate-300" />}
                    </td>
                  </tr>
                  {expandedId === c.example_id && (
                    <tr key={`${c.example_id}-detail`} className="bg-slate-50">
                      <td colSpan={7} className="px-6 py-4">
                        <div className="grid grid-cols-2 gap-6">
                          <div>
                            <h4 className="text-xs font-semibold text-red-600 uppercase mb-2">{t('badResponse')}</h4>
                            <p className="text-sm text-slate-700 bg-red-50 rounded-lg p-3 border border-red-100">
                              {c.bad_response}
                            </p>
                          </div>
                          <div>
                            <h4 className="text-xs font-semibold text-emerald-600 uppercase mb-2">{t('goodResponse')}</h4>
                            <p className="text-sm text-slate-700 bg-emerald-50 rounded-lg p-3 border border-emerald-100">
                              {c.good_response}
                            </p>
                          </div>
                        </div>
                        <div className="flex gap-4 mt-3 text-xs text-slate-500">
                          <span>Persona: <strong>{c.persona}</strong></span>
                          <span>Agent: <strong>{c.agent_type}</strong></span>
                          <span>Cat: <strong>{c.metadata?.category || '-'}</strong></span>
                          <span>{t('correctionDate')}: <strong>{c.metadata?.correction_date || '-'}</strong></span>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3 bg-slate-50 border-t border-slate-200 text-xs text-slate-500">
            {t('correctionsCount', { count: corrections.length })}
          </div>
        </div>
      )}
    </div>
  );
}
