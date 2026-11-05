'use client';

import clsx from 'clsx';
import { File as FileIcon, FileText, ImageIcon, Layers, Mail, type LucideIcon } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { getMediaUrl } from '@/lib/api';
import type { CaseDocument, DocumentKind } from '@/lib/documentFiles';
import { previewUrl } from '@/lib/media';
import type { BatchSummary, MarkdownPage } from '@/lib/types';

export const KIND_ICON: Record<DocumentKind, LucideIcon> = {
  pdf: FileText,
  email: Mail,
  image: ImageIcon,
  other: FileIcon,
};

const SECTION_TITLE = 'px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wider text-slate-500';
const ROW = 'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors';

interface DocumentNavigatorProps {
  applicationId: string;
  documents: CaseDocument<MarkdownPage>[];
  selectedPageNumber: number;
  /** Pages and batch summaries matching the current search. */
  matchingPages: Set<number>;
  matchingBatches: Set<number>;
  batchSummaries: BatchSummary[];
  onSelectPage: (pageNumber: number) => void;
  onSelectBatch: (batchNum: number) => void;
}

function MatchDot() {
  return <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-yellow-500" aria-hidden />;
}

/** Files of the case: a click opens the file in the viewer; the pages of the open file below it. */
export default function DocumentNavigator({
  applicationId,
  documents,
  selectedPageNumber,
  matchingPages,
  matchingBatches,
  batchSummaries,
  onSelectPage,
  onSelectBatch,
}: DocumentNavigatorProps) {
  const t = useTranslations('documentViewer');
  const tNav = useTranslations('pageNavigator');
  const locale = useLocale();
  const files = documents.filter((doc) => doc.kind !== 'image');
  const photos = documents.filter((doc) => doc.kind === 'image');
  const isOpen = (doc: CaseDocument<MarkdownPage>) => doc.pages.some((page) => page.page_number === selectedPageNumber);
  const hasMatch = (doc: CaseDocument<MarkdownPage>) => doc.pages.some((page) => matchingPages.has(page.page_number));
  const open = (doc: CaseDocument<MarkdownPage>) => {
    if (!isOpen(doc)) onSelectPage(doc.pages[0].page_number);
  };
  const rowClass = (selected: boolean) =>
    clsx(ROW, selected ? 'bg-indigo-100 text-indigo-900' : 'text-slate-700 hover:bg-slate-200/60');

  return (
    <nav aria-label={t('documents', { count: documents.length })} className="flex w-60 flex-shrink-0 flex-col overflow-hidden border-r border-gray-200 bg-gray-50">
      <div className="flex-1 overflow-y-auto pb-3">
        {files.length > 0 && (
          <section>
            <h3 className={SECTION_TITLE}>{t('documents', { count: files.length })}</h3>
            <ul className="space-y-0.5 px-1.5">
              {files.map((doc) => {
                const Icon = KIND_ICON[doc.kind];
                const selected = isOpen(doc);
                return (
                  <li key={doc.file}>
                    <button type="button" onClick={() => open(doc)} aria-current={selected ? 'page' : undefined} title={doc.name} className={rowClass(selected)}>
                      <Icon className={clsx('h-4 w-4 flex-shrink-0', selected ? 'text-indigo-600' : 'text-slate-400')} aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{doc.name}</span>
                        <span className="flex items-center gap-1.5 text-xs text-slate-500">
                          {doc.kind === 'email' ? t('email') : t('pageCount', { count: doc.pages.length })}
                          {doc.language && doc.language !== locale && (
                            <span
                              className="rounded bg-slate-200 px-1 text-[10px] font-semibold uppercase text-slate-600"
                              title={t('originalLanguage', { language: doc.language.toUpperCase() })}
                            >
                              {doc.language}
                            </span>
                          )}
                        </span>
                      </span>
                      {hasMatch(doc) && <MatchDot />}
                    </button>
                    {selected && doc.pages.length > 1 && (
                      <div className="flex flex-wrap gap-1 pb-1.5 pl-8 pr-2 pt-1">
                        {doc.pages.map((page, index) => {
                          const current = page.page_number === selectedPageNumber;
                          return (
                            <button
                              key={page.page_number}
                              type="button"
                              onClick={() => onSelectPage(page.page_number)}
                              aria-current={current ? 'page' : undefined}
                              aria-label={t('pageChip', { page: index + 1 })}
                              className={clsx(
                                'relative h-6 min-w-[1.5rem] rounded px-1.5 text-xs font-medium tabular-nums transition-colors',
                                current ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 ring-1 ring-inset ring-slate-200 hover:bg-slate-100',
                              )}
                            >
                              {index + 1}
                              {matchingPages.has(page.page_number) && (
                                <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-yellow-500" aria-hidden />
                              )}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {photos.length > 0 && (
          <section className="mt-1">
            <h3 className={SECTION_TITLE}>{t('photos', { count: photos.length })}</h3>
            <ul className="space-y-0.5 px-1.5">
              {photos.map((doc) => {
                const selected = isOpen(doc);
                const url = getMediaUrl(`/api/applications/${applicationId}/files/${encodeURIComponent(doc.file)}`);
                return (
                  <li key={doc.file}>
                    <button type="button" onClick={() => open(doc)} aria-current={selected ? 'page' : undefined} title={doc.name} className={rowClass(selected)}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={previewUrl(url, 'thumb')} alt="" loading="lazy" decoding="async" className="h-8 w-8 flex-shrink-0 rounded object-cover ring-1 ring-slate-200" />
                      <span className="min-w-0 flex-1 truncate text-xs font-medium">{doc.name}</span>
                      {hasMatch(doc) && <MatchDot />}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {batchSummaries.length > 0 && (
          <section className="mt-1 border-t border-gray-200">
            <h3 className={clsx(SECTION_TITLE, 'flex items-center gap-1.5')}>
              <Layers className="h-3 w-3" aria-hidden />
              {tNav('summaries')}
            </h3>
            <ul className="space-y-0.5 px-1.5">
              {batchSummaries.map((batch) => (
                <li key={batch.batch_num}>
                  <button type="button" onClick={() => onSelectBatch(batch.batch_num)} className={rowClass(false)}>
                    <span className="min-w-0 flex-1 truncate">
                      {tNav('batchLabel', { num: batch.batch_num, start: batch.page_start, end: batch.page_end })}
                    </span>
                    {matchingBatches.has(batch.batch_num) && <MatchDot />}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </nav>
  );
}
