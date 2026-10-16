'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Search, X, ChevronUp, ChevronDown } from 'lucide-react';
import type { MarkdownPage, BatchSummary } from '@/lib/types';
import { useTranslations } from 'next-intl';

export interface SearchResult {
  type: 'page' | 'batch';
  pageNumber?: number;
  batchNum?: number;
  matchCount: number;
  snippets: string[];
}

interface SearchBarProps {
  pages: MarkdownPage[];
  batchSummaries: BatchSummary[];
  onResults: (results: SearchResult[], query: string) => void;
  onNavigate: (result: SearchResult) => void;
}

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function countOccurrences(text: string, query: string): number {
  if (!query) return 0;
  const regex = new RegExp(escapeRegex(query), 'gi');
  return (text.match(regex) || []).length;
}

function extractSnippets(text: string, query: string, maxSnippets: number): string[] {
  const snippets: string[] = [];
  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  let startIdx = 0;

  while (snippets.length < maxSnippets) {
    const idx = lowerText.indexOf(lowerQuery, startIdx);
    if (idx === -1) break;
    const snippetStart = Math.max(0, idx - 30);
    const snippetEnd = Math.min(text.length, idx + query.length + 30);
    let snippet = text.slice(snippetStart, snippetEnd).trim();
    if (snippetStart > 0) snippet = '...' + snippet;
    if (snippetEnd < text.length) snippet = snippet + '...';
    snippets.push(snippet);
    startIdx = idx + query.length;
  }
  return snippets;
}

export function searchSourceContent(
  query: string,
  pages: MarkdownPage[],
  batchSummaries: BatchSummary[]
): SearchResult[] {
  if (!query || query.length < 2) return [];
  const results: SearchResult[] = [];

  for (const page of pages) {
    const matches = countOccurrences(page.markdown, query);
    if (matches > 0) {
      results.push({
        type: 'page',
        pageNumber: page.page_number,
        matchCount: matches,
        snippets: extractSnippets(page.markdown, query, 2),
      });
    }
  }

  for (const batch of batchSummaries) {
    const matches = countOccurrences(batch.summary, query);
    if (matches > 0) {
      results.push({
        type: 'batch',
        batchNum: batch.batch_num,
        matchCount: matches,
        snippets: extractSnippets(batch.summary, query, 2),
      });
    }
  }

  return results;
}

export default function SearchBar({ pages, batchSummaries, onResults, onNavigate }: SearchBarProps) {
  const t = useTranslations('searchBar');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [currentMatchIdx, setCurrentMatchIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const totalMatches = results.reduce((sum, r) => sum + r.matchCount, 0);

  const doSearch = useCallback(
    (q: string) => {
      const res = searchSourceContent(q, pages, batchSummaries);
      setResults(res);
      setCurrentMatchIdx(0);
      onResults(res, q);
    },
    [pages, batchSummaries, onResults]
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, doSearch]);

  const navigateToMatch = (idx: number) => {
    if (results.length === 0) return;
    const wrapped = ((idx % results.length) + results.length) % results.length;
    setCurrentMatchIdx(wrapped);
    onNavigate(results[wrapped]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      navigateToMatch(currentMatchIdx + 1);
    } else if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      navigateToMatch(currentMatchIdx - 1);
    } else if (e.key === 'Escape') {
      setQuery('');
      setResults([]);
      onResults([], '');
      inputRef.current?.blur();
    }
  };

  const clearSearch = () => {
    setQuery('');
    setResults([]);
    onResults([], '');
    inputRef.current?.focus();
  };

  // Global keyboard shortcut for Ctrl+F or /
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey && e.key === 'f') || (e.key === '/' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement))) {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <div className="border-b border-gray-200 bg-white px-4 py-2.5">
      <div className="flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('placeholder')}
            className="w-full pl-9 pr-20 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-gray-50"
          />
          {query && (
            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
              <span className="text-xs text-gray-500 mr-1">
                {totalMatches > 0
                  ? t('resultsCount', { current: currentMatchIdx + 1, total: results.length })
                  : t('noMatches')}
              </span>
              <button
                onClick={() => navigateToMatch(currentMatchIdx - 1)}
                className="p-0.5 hover:bg-gray-200 rounded"
                title={t('previousMatch')}
              >
                <ChevronUp className="w-3.5 h-3.5 text-gray-500" />
              </button>
              <button
                onClick={() => navigateToMatch(currentMatchIdx + 1)}
                className="p-0.5 hover:bg-gray-200 rounded"
                title={t('nextMatch')}
              >
                <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
              </button>
              <button
                onClick={clearSearch}
                className="p-0.5 hover:bg-gray-200 rounded"
                title={t('clearSearch')}
              >
                <X className="w-3.5 h-3.5 text-gray-500" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Match chips */}
      {results.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          <span className="text-xs text-gray-500">Matches:</span>
          {results.map((r, idx) => (
            <button
              key={`${r.type}-${r.pageNumber ?? r.batchNum}`}
              onClick={() => {
                setCurrentMatchIdx(idx);
                onNavigate(r);
              }}
              className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                idx === currentMatchIdx
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-blue-100 hover:text-blue-700'
              }`}
            >
              {r.type === 'page' ? `Page ${r.pageNumber}` : `Batch ${r.batchNum}`}
              {r.matchCount > 1 && ` (${r.matchCount})`}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
