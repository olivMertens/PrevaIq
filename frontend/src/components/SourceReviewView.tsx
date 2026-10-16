'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import type { ApplicationMetadata } from '@/lib/types';
import SearchBar, { type SearchResult } from './SearchBar';
import PageNavigator from './PageNavigator';
import InlinePdfViewer from './InlinePdfViewer';
import ExtractedTextPane from './ExtractedTextPane';
import { FileStack } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface SourceReviewViewProps {
  application: ApplicationMetadata;
  initialPage?: number;
}

export default function SourceReviewView({ application, initialPage }: SourceReviewViewProps) {
  const t = useTranslations('common');
  // Use markdown_pages if available, otherwise synthesize from document_markdown
  const pages = useMemo(() => {
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

  // Search state
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  // Current page object
  const currentPage = useMemo(
    () => pages.find((p) => p.page_number === selectedPageNum) || null,
    [pages, selectedPageNum]
  );

  // Current file name for pdf viewer
  const currentFileName = currentPage?.file || (pages.length > 0 ? pages[0].file : '');

  // Compute the 0-based index of the current page within its file
  // (used for PDF #page= fragment which needs the file-internal page number)
  const filePageIndex = useMemo(() => {
    if (!currentPage) return 0;
    const filePages = pages.filter((p) => p.file === currentPage.file);
    return filePages.indexOf(currentPage);
  }, [pages, currentPage]);

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
  if (pages.length === 0) {
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

      {/* Three-column layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Page Navigator */}
        <PageNavigator
          pages={pages}
          batchSummaries={batchSummaries}
          selectedPageNumber={selectedPageNum}
          searchResults={searchResults}
          searchQuery={searchQuery}
          onSelectPage={goToPage}
          onSelectBatch={goToBatch}
        />

        {/* Center: PDF Preview */}
        <div className="flex-1 min-w-0 border-r border-gray-200">
          <InlinePdfViewer
            applicationId={application.id}
            fileName={currentFileName}
            pageNumber={currentPage?.page_number || 1}
            totalPages={pages.length}
            filePageIndex={filePageIndex}
            onPrevPage={goToPrevPage}
            onNextPage={goToNextPage}
          />
        </div>

        {/* Right: Extracted Text + Batch Summary */}
        <div className="flex-1 min-w-0">
          <ExtractedTextPane
            page={currentPage}
            batchSummary={contextualBatch}
            searchQuery={searchQuery}
          />
        </div>
      </div>
    </div>
  );
}
