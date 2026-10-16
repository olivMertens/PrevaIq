'use client';

import { useMemo } from 'react';
import { FileText, ImageIcon, ChevronDown, ChevronRight, Layers } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { MarkdownPage, BatchSummary } from '@/lib/types';
import type { SearchResult } from './SearchBar';
import clsx from 'clsx';
import { useState } from 'react';

interface PageNavigatorProps {
  pages: MarkdownPage[];
  batchSummaries: BatchSummary[];
  selectedPageNumber: number;
  searchResults: SearchResult[];
  searchQuery: string;
  onSelectPage: (pageNumber: number) => void;
  onSelectBatch: (batchNum: number) => void;
}

export default function PageNavigator({
  pages,
  batchSummaries,
  selectedPageNumber,
  searchResults,
  searchQuery,
  onSelectPage,
  onSelectBatch,
}: PageNavigatorProps) {
  const t = useTranslations('pageNavigator');
  const [collapsedFiles, setCollapsedFiles] = useState<Set<string>>(new Set());

  // Group pages by file
  const pagesByFile = useMemo(() => {
    const grouped: Record<string, MarkdownPage[]> = {};
    pages.forEach((page) => {
      const key = page.file || 'Unknown';
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(page);
    });
    return grouped;
  }, [pages]);

  // Set of page numbers that have search matches
  const matchingPages = useMemo(() => {
    const set = new Set<number>();
    searchResults
      .filter((r) => r.type === 'page' && r.pageNumber != null)
      .forEach((r) => set.add(r.pageNumber!));
    return set;
  }, [searchResults]);

  // Set of batch nums that have search matches
  const matchingBatches = useMemo(() => {
    const set = new Set<number>();
    searchResults
      .filter((r) => r.type === 'batch' && r.batchNum != null)
      .forEach((r) => set.add(r.batchNum!));
    return set;
  }, [searchResults]);

  const toggleFile = (fileName: string) => {
    const next = new Set(collapsedFiles);
    next.has(fileName) ? next.delete(fileName) : next.add(fileName);
    setCollapsedFiles(next);
  };

  const shortName = (fileName: string) => {
    const parts = fileName.split('/');
    return parts[parts.length - 1] || fileName;
  };

  const isImageFile = (fileName: string) => {
    const ext = fileName.split('.').pop()?.toLowerCase() || '';
    return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'tif'].includes(ext);
  };

  return (
    <div className="w-44 border-r border-gray-200 bg-gray-50 flex flex-col overflow-hidden">
      <div className="px-3 py-2.5 border-b border-gray-200 bg-white">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('pages')}</h3>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* File groups */}
        {Object.entries(pagesByFile).map(([fileName, filePages]) => {
          const isCollapsed = collapsedFiles.has(fileName);
          const isImg = isImageFile(fileName);
          const FileIcon = isImg ? ImageIcon : FileText;
          // Single-page image files: clicking the header selects the page directly
          const isSingleImagePage = isImg && filePages.length === 1;
          const isHeaderSelected = isSingleImagePage && filePages[0].page_number === selectedPageNumber;
          return (
            <div key={fileName} className="py-1">
              <button
                onClick={() => isSingleImagePage ? onSelectPage(filePages[0].page_number) : toggleFile(fileName)}
                className={clsx(
                  'flex items-center gap-1.5 w-full px-3 py-1.5 text-xs font-medium transition-colors',
                  isHeaderSelected
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                )}
                title={fileName}
              >
                {!isSingleImagePage && (isCollapsed ? (
                  <ChevronRight className="w-3 h-3 flex-shrink-0" />
                ) : (
                  <ChevronDown className="w-3 h-3 flex-shrink-0" />
                ))}
                <FileIcon className="w-3 h-3 flex-shrink-0" />
                <span className="truncate">{shortName(fileName)}</span>
              </button>

              {!isSingleImagePage && !isCollapsed && (
                <ul className="px-2 space-y-0.5">
                  {filePages.map((page) => {
                    const isSelected = page.page_number === selectedPageNumber;
                    const hasMatch = searchQuery.length >= 2 && matchingPages.has(page.page_number);
                    return (
                      <li key={page.page_number}>
                        <button
                          onClick={() => onSelectPage(page.page_number)}
                          className={clsx(
                            'w-full text-left px-3 py-1.5 text-sm rounded transition-colors flex items-center gap-2',
                            isSelected
                              ? 'bg-blue-100 text-blue-700 font-medium'
                              : 'text-gray-700 hover:bg-gray-100'
                          )}
                        >
                          {hasMatch && (
                            <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 flex-shrink-0" />
                          )}
                          <span>{t('pageLabel', { num: page.page_number })}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}

        {/* Batch summaries section */}
        {batchSummaries.length > 0 && (
          <div className="border-t border-gray-200 py-1 mt-1">
            <div className="px-3 py-1.5 flex items-center gap-1.5">
              <Layers className="w-3 h-3 text-gray-400" />
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                {t('summaries')}
              </span>
            </div>
            <ul className="px-2 space-y-0.5">
              {batchSummaries.map((batch) => {
                const hasMatch = searchQuery.length >= 2 && matchingBatches.has(batch.batch_num);
                return (
                  <li key={batch.batch_num}>
                    <button
                      onClick={() => onSelectBatch(batch.batch_num)}
                      className="w-full text-left px-3 py-1.5 text-sm rounded text-gray-700 hover:bg-gray-100 transition-colors flex items-center gap-2"
                    >
                      {hasMatch && (
                        <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 flex-shrink-0" />
                      )}
                      <span className="truncate">
                        {t('batchLabel', { num: batch.batch_num, start: batch.page_start, end: batch.page_end })}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
