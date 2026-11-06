'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import type { ApplicationMetadata, MarkdownPage } from '@/lib/types';
import SearchBar, { type SearchResult } from './SearchBar';
import DocumentNavigator from './DocumentNavigator';
import DocumentViewer from './DocumentViewer';
import ExtractedTextPane from './ExtractedTextPane';
import type { ContentView } from './ContentLanguageBar';
import { usePersistentChoice } from './case/usePersistentState';
import { groupDocuments, translationOrder } from '@/lib/documentFiles';
import { useContentTranslation, type TranslatableItem } from '@/lib/useContentTranslation';
import { FileStack } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { sameLanguage } from '@/i18n/locales';

const CONTENT_VIEWS: readonly ContentView[] = ['translated', 'original'];
// Pages of the open document translated at once (around the page being read in longer ones).
const DOCUMENT_TRANSLATION_LIMIT = 24;

/** Content written in another language than the UI (unclear languages are left as they are). */
function isForeign(language: string | null | undefined, locale: string): language is string {
  return !!language && !sameLanguage(language, locale);
}

function pageItem(page: MarkdownPage): TranslatableItem {
  return { kind: 'page', id: page.page_number, text: page.markdown };
}

interface SourceReviewViewProps {
  application: ApplicationMetadata;
  initialPage?: number;
  /** Page being read, kept in the address bar so that a reload reopens it. */
  onPageChange?: (pageNumber: number) => void;
}

export default function SourceReviewView({ application, initialPage, onPageChange }: SourceReviewViewProps) {
  const t = useTranslations('common');
  // Use markdown_pages if available, otherwise synthesize from document_markdown
  const pages = useMemo<MarkdownPage[]>(() => {
    if (application.markdown_pages && application.markdown_pages.length > 0) {
      return application.markdown_pages;
    }
    // Fallback: create a single page from document_markdown
    if (application.document_markdown) {
      return [{
        page_number: 1,
        file: application.files?.[0]?.filename || 'document',
        markdown: application.document_markdown,
      }];
    }
    return [];
  }, [application.markdown_pages, application.document_markdown, application.files]);
  const documents = useMemo(() => groupDocuments(pages), [pages]);
  const batchSummaries = application.batch_summaries || [];

  // Selected page number (1-indexed)
  const [selectedPageNum, setSelectedPageNum] = useState<number>(
    initialPage || (pages.length > 0 ? pages[0].page_number : 1)
  );

  // Jump to initialPage when it changes
  useEffect(() => {
    if (initialPage && initialPage !== selectedPageNum) {
      setSelectedPageNum(initialPage);
    }
  }, [initialPage]);

  useEffect(() => {
    onPageChange?.(selectedPageNum);
  }, [onPageChange, selectedPageNum]);

  // Search state
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  const currentDocument = useMemo(
    () => documents.find((doc) => doc.pages.some((page) => page.page_number === selectedPageNum)) ?? documents[0] ?? null,
    [documents, selectedPageNum],
  );
  const pageIndex = currentDocument
    ? Math.max(0, currentDocument.pages.findIndex((page) => page.page_number === selectedPageNum))
    : 0;
  const currentPage = currentDocument?.pages[pageIndex] ?? null;
  const globalIndex = pages.findIndex((page) => page.page_number === currentPage?.page_number);

  // Find the batch summary that covers the current page
  const contextualBatch = useMemo(() => {
    if (!currentPage || batchSummaries.length === 0) return null;
    return (
      batchSummaries.find(
        (b) =>
          currentPage.page_number >= b.page_start && currentPage.page_number <= b.page_end
      ) || null
    );
  }, [currentPage, batchSummaries]);

  // Content in another language is shown translated into the UI language (original on demand),
  // a whole document at a time so that reading it is never interrupted.
  const locale = useLocale();
  const [contentView, setContentView] = usePersistentChoice<ContentView>(
    'prevaiq.content.view',
    'translated',
    CONTENT_VIEWS,
  );
  const readingOrder = useMemo(
    () => (currentDocument ? translationOrder(currentDocument.pages, selectedPageNum, DOCUMENT_TRANSLATION_LIMIT) : []),
    [currentDocument, selectedPageNum],
  );
  const batchItem = useMemo<TranslatableItem | null>(
    () =>
      contextualBatch && isForeign(contextualBatch.language, locale)
        ? { kind: 'batch', id: contextualBatch.batch_num, text: contextualBatch.summary }
        : null,
    [contextualBatch, locale],
  );
  const translationItems = useMemo<TranslatableItem[]>(() => {
    if (contentView !== 'translated') return [];
    const items = readingOrder.filter((page) => isForeign(page.language, locale)).map(pageItem);
    // The summary of the pages being read comes right after the first page.
    if (batchItem) items.splice(1, 0, batchItem);
    return items;
  }, [contentView, readingOrder, batchItem, locale]);
  const translationOf = useContentTranslation(application.id, locale, translationItems);
  const requested = useMemo(() => new Set(readingOrder.map((page) => page.page_number)), [readingOrder]);
  const pageTranslation = (page: MarkdownPage) =>
    isForeign(page.language, locale) && (contentView === 'original' || requested.has(page.page_number))
      ? translationOf(pageItem(page))
      : null;

  // Page navigation
  const goToPage = useCallback(
    (pageNum: number) => {
      const exists = pages.find((p) => p.page_number === pageNum);
      if (exists) setSelectedPageNum(pageNum);
    },
    [pages]
  );

  const goToPrevPage = useCallback(() => {
    const idx = pages.findIndex((p) => p.page_number === selectedPageNum);
    if (idx > 0) setSelectedPageNum(pages[idx - 1].page_number);
  }, [pages, selectedPageNum]);

  const goToNextPage = useCallback(() => {
    const idx = pages.findIndex((p) => p.page_number === selectedPageNum);
    if (idx >= 0 && idx < pages.length - 1) setSelectedPageNum(pages[idx + 1].page_number);
  }, [pages, selectedPageNum]);

  // An e-mail attachment that is also a file of the case opens in the viewer.
  const openFile = useCallback(
    (fileName: string) => {
      const wanted = fileName.toLowerCase();
      const doc = documents.find((item) => item.file.toLowerCase() === wanted || item.name.toLowerCase() === wanted);
      if (doc) setSelectedPageNum(doc.pages[0].page_number);
    },
    [documents]
  );

  // Batch selection → navigate to first page of that batch
  const goToBatch = useCallback(
    (batchNum: number) => {
      const batch = batchSummaries.find((b) => b.batch_num === batchNum);
      if (batch) setSelectedPageNum(batch.page_start);
    },
    [batchSummaries]
  );

  // Search callbacks
  const handleSearchResults = useCallback((_results: SearchResult[], query: string) => {
    setSearchResults(_results);
    setSearchQuery(query);
  }, []);

  const handleSearchNavigate = useCallback(
    (result: SearchResult) => {
      if (result.type === 'page' && result.pageNumber != null) {
        goToPage(result.pageNumber);
      } else if (result.type === 'batch' && result.batchNum != null) {
        goToBatch(result.batchNum);
      }
    },
    [goToPage, goToBatch]
  );

  const { matchingPages, matchingBatches } = useMemo(() => {
    const active = searchQuery.length >= 2;
    return {
      matchingPages: new Set(active ? searchResults.flatMap((r) => (r.type === 'page' && r.pageNumber != null ? [r.pageNumber] : [])) : []),
      matchingBatches: new Set(active ? searchResults.flatMap((r) => (r.type === 'batch' && r.batchNum != null ? [r.batchNum] : [])) : []),
    };
  }, [searchResults, searchQuery]);

  // Keyboard shortcuts for page navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goToPrevPage();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        goToNextPage();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [goToPrevPage, goToNextPage]);

  // Empty state
  if (pages.length === 0 || !currentDocument) {
    return (
      <div className="flex-1 flex items-center justify-center bg-white rounded-xl border border-gray-200 m-6">
        <div className="text-center py-12 text-gray-500">
          <FileStack className="w-12 h-12 mx-auto mb-2 text-gray-400" />
          <p className="font-medium">{t('noExtractedContent')}</p>
          <p className="text-sm mt-2">
            {t('runExtractionHint')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Search bar */}
      <SearchBar
        pages={pages}
        batchSummaries={batchSummaries}
        onResults={handleSearchResults}
        onNavigate={handleSearchNavigate}
      />

      {/* Three-column layout: files, original document, text */}
      <div className="flex-1 flex overflow-hidden">
        <DocumentNavigator
          applicationId={application.id}
          documents={documents}
          selectedPageNumber={currentPage?.page_number ?? selectedPageNum}
          matchingPages={matchingPages}
          matchingBatches={matchingBatches}
          batchSummaries={batchSummaries}
          onSelectPage={goToPage}
          onSelectBatch={goToBatch}
        />

        <div className="flex-1 min-w-0 border-r border-gray-200">
          <DocumentViewer
            applicationId={application.id}
            document={currentDocument}
            pageIndex={pageIndex}
            hasPrevious={globalIndex > 0}
            hasNext={globalIndex >= 0 && globalIndex < pages.length - 1}
            onPrevious={goToPrevPage}
            onNext={goToNextPage}
            onOpenFile={openFile}
          />
        </div>

        <div className="flex-1 min-w-0">
          <ExtractedTextPane
            document={currentDocument}
            selectedPageNumber={currentPage?.page_number ?? selectedPageNum}
            batchSummary={contextualBatch}
            searchQuery={searchQuery}
            contentView={contentView}
            onContentViewChange={setContentView}
            pageTranslation={pageTranslation}
            batchTranslation={batchItem ? translationOf(batchItem) : null}
            onSelectPage={goToPage}
          />
        </div>
      </div>
    </div>
  );
}
