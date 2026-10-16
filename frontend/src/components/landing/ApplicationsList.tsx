'use client';

import {
  FileText,
  Loader2,
  Search,
  LayoutGrid,
  List as ListIcon,
  ChevronRight,
  ChevronLeft,
  Calendar,
  Hash,
  Filter,
  Paperclip,
  User,
  FileCheck,
} from 'lucide-react';
import { CSSProperties, useState, useMemo } from 'react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import { ApplicationListItem } from '@/lib/types';
import StatusBadge from './StatusBadge';

const PAGE_SIZE = 10;

// Extract display name from key_fields
function getInsuredName(kf?: Record<string, string>): string | null {
  if (!kf) return null;
  return (
    kf.NomAssure || kf.AssuréNom || kf.InsuredName || kf.Assure || kf.Assuré ||
    kf.NomClient || kf.ClientName || kf.PolicyholderName || kf.NomSouscripteur ||
    kf.ApplicantName || kf.PatientName || kf.Claimant || kf.ClaimantName ||
    kf.Conducteur || kf.DriverName || kf.NomConducteur || kf.Borrower ||
    kf.BorrowerName || kf.BorrowerFullName || kf.Emprunteur || null
  );
}

function getClaimType(kf?: Record<string, string>): string | null {
  if (!kf) return null;
  const vehicle = [kf.VehicleMake, kf.VehicleModel].filter(Boolean).join(' ').trim();
  return (
    kf.NatureSinistre || kf.CauseOfLoss || kf.ClaimType || kf.LossType ||
    kf.IncidentDescription || kf.FormuleDemandee || kf.PolicyProduct ||
    kf.CoverageType || kf.OverallDamageSeverity || kf.EstimatedDamageCategory ||
    vehicle || kf.ClaimNumber || kf.LicensePlate || null
  );
}

const STATUS_FILTERS = [
  { key: 'all', color: 'bg-slate-100 text-slate-700' },
  { key: 'completed', color: 'bg-emerald-100 text-emerald-700' },
  { key: 'processing', color: 'bg-sky-100 text-sky-700' },
  { key: 'error', color: 'bg-rose-100 text-rose-700' },
  { key: 'pending', color: 'bg-amber-100 text-amber-700' },
] as const;

interface ApplicationsListProps {
  applications: ApplicationListItem[];
  loading: boolean;
  personaPrimaryColor: string;
  getAppDisplayTitle: (app: ApplicationListItem) => string;
  onSelectApp: (appId: string) => void;
}

export default function ApplicationsList({
  applications,
  loading,
  personaPrimaryColor,
  getAppDisplayTitle,
  onSelectApp,
}: ApplicationsListProps) {
  const t = useTranslations('dashboard');
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('list');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [page, setPage] = useState(1);

  const filteredApps = useMemo(() => applications.filter(app => {
    const search = searchQuery.toLowerCase();
    const matchesSearch =
      app.id.toLowerCase().includes(search) ||
      app.external_reference?.toLowerCase().includes(search) ||
      app.summary_title?.toLowerCase().includes(search) ||
      Object.values(app.key_fields || {}).some((value) => value.toLowerCase().includes(search));
    if (!matchesSearch) return false;
    if (statusFilter === 'all') return true;
    if (statusFilter === 'processing') return app.status !== 'completed' && app.status !== 'error' && app.status !== 'pending' && app.status !== 'uploaded';
    if (statusFilter === 'pending') return app.status === 'pending' || app.status === 'uploaded' || app.status === 'pending_review';
    return app.status === statusFilter;
  }), [applications, searchQuery, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredApps.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pagedApps = filteredApps.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const handleFilterChange = (f: string) => { setStatusFilter(f); setPage(1); };
  const handleSearchChange = (v: string) => { setSearchQuery(v); setPage(1); };

  return (
    <div className="max-w-7xl 2xl:max-w-[96rem] mx-auto px-6 lg:px-8 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 gap-4">
        <h2 className="text-lg font-semibold text-slate-900">
          {t('recentApplications')}
          <span className="ml-2 text-sm font-normal text-slate-500">({filteredApps.length})</span>
        </h2>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative flex-1 sm:flex-initial">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input type="text" placeholder={t('searchCases')} value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="pl-9 pr-4 py-2 border border-slate-200 rounded-lg text-sm w-full sm:w-64 focus:outline-none focus:ring-2 bg-white"
              style={{ '--tw-ring-color': personaPrimaryColor } as CSSProperties} />
          </div>
          <div className="bg-white border border-slate-200 rounded-lg p-1 flex">
            <button onClick={() => setViewMode('grid')}
              className={clsx("p-1.5 rounded transition-colors", viewMode === 'grid' ? "bg-slate-100 text-slate-900" : "text-slate-400 hover:text-slate-600")}>
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button onClick={() => setViewMode('list')}
              className={clsx("p-1.5 rounded transition-colors", viewMode === 'list' ? "bg-slate-100 text-slate-900" : "text-slate-400 hover:text-slate-600")}>
              <ListIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Status Filter Pills */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <Filter className="w-4 h-4 text-slate-400" />
        {STATUS_FILTERS.map(f => (
          <button key={f.key} onClick={() => handleFilterChange(f.key)}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition-all',
              statusFilter === f.key ? `${f.color} ring-1 ring-offset-1` : 'bg-white text-slate-500 border border-slate-200 hover:bg-slate-50'
            )}>
            {f.key === 'all' ? t('filter_all') : f.key === 'completed' ? t('filter_completed') : f.key === 'processing' ? t('filter_processing') : f.key === 'error' ? t('filter_error') : t('filter_pending')}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex justify-center py-20 bg-white rounded-xl border border-slate-200">
          <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
        </div>
      ) : filteredApps.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-slate-200 border-dashed">
          <FileText className="w-12 h-12 text-slate-300 mx-auto mb-3" />
          <h3 className="text-lg font-medium text-slate-900">{t('noApplications')}</h3>
          <p className="text-slate-500 mt-1">{t('noApplicationsHint')}</p>
        </div>
      ) : viewMode === 'list' ? (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm overflow-x-auto">
          <table className="w-full text-left text-sm min-w-[640px]">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-6 py-3 font-medium text-slate-600">{t('headerDossier')}</th>
                <th className="px-6 py-3 font-medium text-slate-600">{t('headerStatus')}</th>
                <th className="px-6 py-3 font-medium text-slate-600">{t('headerCreated')}</th>
                <th className="px-6 py-3 font-medium text-slate-600">{t('headerReference')}</th>
                <th className="px-6 py-3 font-medium text-slate-600">{t('headerFiles')}</th>
                <th className="px-6 py-3 font-medium text-slate-600 text-right">{t('headerAction')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pagedApps.map((app) => (
                <tr key={app.id} onClick={() => onSelectApp(app.id)}
                  className="hover:bg-slate-50 cursor-pointer transition-colors group">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ backgroundColor: `${personaPrimaryColor}10` }}>
                        <FileText className="w-4 h-4" style={{ color: personaPrimaryColor }} />
                      </div>
                      <div>
                        <div className="font-medium text-slate-900 transition-colors">{getAppDisplayTitle(app)}</div>
                        <div className="text-xs text-slate-400 font-mono flex items-center gap-1">
                          <Hash className="w-3 h-3" />{app.id.substring(0, 8)}
                          {getInsuredName(app.key_fields) && (
                            <><span className="mx-1">•</span><User className="w-3 h-3" /><span className="text-slate-500 font-sans">{getInsuredName(app.key_fields)}</span></>
                          )}
                        </div>
                        {getClaimType(app.key_fields) && (
                          <div className="text-xs text-slate-500 mt-0.5">{getClaimType(app.key_fields)}</div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4"><StatusBadge status={app.status} processingStatus={app.processing_status} /></td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1.5 text-slate-500">
                      <Calendar className="w-3.5 h-3.5" /><span>{new Date(app.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">{new Date(app.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                  </td>
                  <td className="px-6 py-4 text-slate-500 max-w-xs">
                    {app.external_reference ? (
                      <span className="font-mono text-xs bg-slate-100 px-2 py-1 rounded">{app.external_reference}</span>
                    ) : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-6 py-4">
                    {(app.file_count ?? 0) > 0 ? (
                      <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                        <Paperclip className="w-3 h-3" />{app.file_count}
                      </span>
                    ) : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className="inline-flex items-center gap-1 text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: personaPrimaryColor }}>
                      {t('open')}<ChevronRight className="w-4 h-4" />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
          {pagedApps.map((app) => (
            <button key={app.id} onClick={() => onSelectApp(app.id)}
              className="bg-white rounded-xl border border-slate-200 p-5 text-left hover:border-slate-300 hover:shadow-md transition-all group flex flex-col">
              <div className="flex justify-between items-start mb-3 w-full">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${personaPrimaryColor}10` }}>
                  <FileText className="w-5 h-5" style={{ color: personaPrimaryColor }} />
                </div>
                <StatusBadge status={app.status} processingStatus={app.processing_status} />
              </div>
              <h3 className="font-semibold text-slate-900 mb-1 line-clamp-1 transition-colors">{getAppDisplayTitle(app)}</h3>
              <div className="text-xs text-slate-400 font-mono flex items-center gap-1 mb-1">
                <Hash className="w-3 h-3" />{app.id.substring(0, 8)}
                {app.external_reference && <><span className="mx-1">•</span><span className="truncate">{app.external_reference}</span></>}
              </div>
              {getInsuredName(app.key_fields) && (
                <div className="text-xs text-slate-600 flex items-center gap-1 mb-0.5">
                  <User className="w-3 h-3 text-slate-400" />{getInsuredName(app.key_fields)}
                </div>
              )}
              {getClaimType(app.key_fields) && (
                <div className="text-xs text-slate-500 mb-1">{getClaimType(app.key_fields)}</div>
              )}
              <div className="mt-auto pt-3 border-t border-slate-100 flex justify-between items-center text-sm text-slate-500 w-full">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" /><span>{new Date(app.created_at).toLocaleDateString()}</span></div>
                  {(app.file_count ?? 0) > 0 && (
                    <div className="flex items-center gap-1 text-xs text-slate-400"><Paperclip className="w-3 h-3" />{app.file_count}</div>
                  )}
                </div>
                <ChevronRight className="w-4 h-4 text-slate-300 group-hover:translate-x-0.5 transition-all" />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-between items-center mt-4 px-2">
          <span className="text-sm text-slate-500">
            {(safePage - 1) * PAGE_SIZE + 1}\u2013{Math.min(safePage * PAGE_SIZE, filteredApps.length)} / {filteredApps.length}
          </span>
          <div className="flex items-center gap-1">
            <button disabled={safePage <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}
              className="p-2 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed">
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).filter(p =>
              p === 1 || p === totalPages || Math.abs(p - safePage) <= 1
            ).map((p, idx, arr) => (
              <span key={p}>
                {idx > 0 && arr[idx - 1] !== p - 1 && <span className="px-1 text-slate-400">\u2026</span>}
                <button onClick={() => setPage(p)}
                  className={clsx('w-8 h-8 rounded-lg text-sm font-medium transition-colors',
                    p === safePage ? 'text-white' : 'text-slate-600 hover:bg-slate-100')}
                  style={p === safePage ? { backgroundColor: personaPrimaryColor } : undefined}>
                  {p}
                </button>
              </span>
            ))}
            <button disabled={safePage >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              className="p-2 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
