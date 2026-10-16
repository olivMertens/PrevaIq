'use client';

import { useMemo, useState } from 'react';
import { Copy, Check, ChevronDown, ChevronUp, FileText, Layers } from 'lucide-react';
import type { MarkdownPage, BatchSummary } from '@/lib/types';
import { useTranslations } from 'next-intl';

interface ExtractedTextPaneProps {
  page: MarkdownPage | null;
  batchSummary: BatchSummary | null;
  searchQuery: string;
}

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Highlight search matches in text with <mark> tags */
function highlightText(text: string, query: string): React.ReactNode[] {
  if (!query || query.length < 2) return [text];
  const parts = text.split(new RegExp(`(${escapeRegex(query)})`, 'gi'));
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase() ? (
      <mark key={i} className="bg-yellow-200 rounded px-0.5">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

/** Simple markdown renderer - converts basic markdown to React elements.
 *  Supports headings, lists, bold, and HTML table blocks from OCR. */
function renderMarkdown(text: string, searchQuery: string): React.ReactNode[] {
  // Strip HTML comments (<!-- ... -->) before processing
  const cleaned = text.replace(/<!--[\s\S]*?-->/g, '');
  const lines = cleaned.split('\n');
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Detect HTML table block — collect all lines until </table>
    if (line.trim().startsWith('<table')) {
      const tableLines: string[] = [];
      while (i < lines.length) {
        tableLines.push(lines[i]);
        if (lines[i].includes('</table>')) { i++; break; }
        i++;
      }
      const tableHtml = tableLines.join('\n');
      elements.push(
        <div
          key={`table-${elements.length}`}
          className="my-3 overflow-x-auto text-sm"
          dangerouslySetInnerHTML={{ __html: sanitizeTableHtml(tableHtml) }}
        />
      );
      continue;
    }

    // Skip standalone HTML tags (tr, td, th) that are outside a table block
    if (line.trim().match(/^<\/?(tr|td|th|table|thead|tbody)\b[^>]*>\s*$/)) {
      i++;
      continue;
    }

    // Headings
    const h3Match = line.match(/^###\s+(.*)/);
    const h2Match = line.match(/^##\s+(.*)/);
    const h1Match = line.match(/^#\s+(.*)/);

    if (h1Match) {
      elements.push(
        <h2 key={i} className="text-lg font-bold text-gray-900 mt-4 mb-2">
          {highlightText(h1Match[1], searchQuery)}
        </h2>
      );
    } else if (h2Match) {
      elements.push(
        <h3 key={i} className="text-base font-semibold text-gray-900 mt-3 mb-1.5">
          {highlightText(h2Match[1], searchQuery)}
        </h3>
      );
    } else if (h3Match) {
      elements.push(
        <h4 key={i} className="text-sm font-semibold text-gray-800 mt-2 mb-1">
          {highlightText(h3Match[1], searchQuery)}
        </h4>
      );
    } else if (line.match(/^\s*[-*]\s+/)) {
      const content = line.replace(/^\s*[-*]\s+/, '');
      elements.push(
        <li key={i} className="text-sm text-gray-700 ml-4 list-disc">
          {highlightInline(content, searchQuery)}
        </li>
      );
    } else if (line.match(/^\s*\d+\.\s+/)) {
      const content = line.replace(/^\s*\d+\.\s+/, '');
      elements.push(
        <li key={i} className="text-sm text-gray-700 ml-4 list-decimal">
          {highlightInline(content, searchQuery)}
        </li>
      );
    } else if (line.trim() === '' || line.trim() === '---') {
      elements.push(<div key={i} className="h-2" />);
    } else {
      // Regular paragraph — strip any remaining inline HTML tags
      const cleanLine = line.replace(/<[^>]+>/g, '').trim();
      if (cleanLine) {
        elements.push(
          <p key={i} className="text-sm text-gray-700 leading-relaxed">
            {highlightInline(cleanLine, searchQuery)}
          </p>
        );
      }
    }
    i++;
  }

  return elements;
}

/** Sanitize HTML table: allow only table-related tags, strip everything else */
function sanitizeTableHtml(html: string): string {
  // Add Tailwind classes to table elements for proper rendering
  return html
    .replace(/<table/g, '<table class="w-full border-collapse border border-slate-300 text-sm"')
    .replace(/<th/g, '<th class="border border-slate-300 bg-slate-100 px-3 py-2 text-left font-semibold text-slate-700"')
    .replace(/<td/g, '<td class="border border-slate-200 px-3 py-1.5 text-slate-700"')
    .replace(/<tr/g, '<tr class="even:bg-slate-50"')
    // Strip dangerous attributes (onclick, onerror, style with expressions)
    .replace(/\s(on\w+|style)\s*=\s*["'][^"']*["']/gi, '');
}

/** Process inline markdown (bold, italic) and search highlighting */
function highlightInline(text: string, searchQuery: string): React.ReactNode[] {
  // First apply bold/italic, then search highlighting
  // Process **bold** patterns
  const parts: React.ReactNode[] = [];
  const boldRegex = /\*\*([^*]+)\*\*/g;
  let lastIndex = 0;
  let match;

  while ((match = boldRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const segment = text.slice(lastIndex, match.index);
      parts.push(...highlightText(segment, searchQuery));
    }
    parts.push(
      <strong key={`b-${match.index}`} className="font-semibold text-gray-900">
        {highlightText(match[1], searchQuery)}
      </strong>
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(...highlightText(text.slice(lastIndex), searchQuery));
  }

  return parts.length > 0 ? parts : highlightText(text, searchQuery);
}

export default function ExtractedTextPane({
  page,
  batchSummary,
  searchQuery,
}: ExtractedTextPaneProps) {
  const t = useTranslations('common');
  const [copied, setCopied] = useState(false);
  const [batchExpanded, setBatchExpanded] = useState(false);

  const handleCopy = async () => {
    if (page?.markdown) {
      await navigator.clipboard.writeText(page.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const shortFileName = (file: string) => {
    const parts = file.split('/');
    return parts[parts.length - 1] || file;
  };

  if (!page) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        <div className="text-center">
          <FileText className="w-10 h-10 mx-auto mb-2 opacity-50" />
          <p>{t('selectPageToView')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-white border-b border-gray-200">
        <div className="min-w-0">
          <div className="text-sm text-gray-600">
            <span className="font-medium text-gray-900">Page {page.page_number}</span>
            {' — '}
            <span>{shortFileName(page.file)}</span>
          </div>
          {(page.extraction_backend || page.analyzer_id || page.source_page_number) && (
            <div className="mt-1 flex flex-wrap gap-1.5 text-[11px] text-slate-500">
              {page.extraction_backend && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5">
                  {t('backend')}: {page.extraction_backend}
                </span>
              )}
              {page.analyzer_id && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5">
                  {t('analyzer')}: {page.analyzer_id}
                </span>
              )}
              {page.source_page_number && page.source_page_number !== page.page_number && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5">
                  {t('sourcePage')}: {page.source_page_number}
                </span>
              )}
            </div>
          )}
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2.5 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-green-600" />
              <span className="text-green-600">{t('copied')}</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>{t('copy')}</span>
            </>
          )}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4 bg-white">
        {/* Contextual batch summary card — shown above extracted text */}
        {batchSummary && (
          <div className="mb-4 pb-4 border-b border-gray-200">
            <div
              className="border border-blue-200 bg-blue-50 rounded-lg overflow-hidden"
            >
              <button
                onClick={() => setBatchExpanded(!batchExpanded)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-blue-100 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-blue-600" />
                  <span className="text-sm font-medium text-blue-900">
                    AI Summary — Batch {batchSummary.batch_num}
                  </span>
                  <span className="text-xs text-blue-600">
                    (Pages {batchSummary.page_start}–{batchSummary.page_end})
                  </span>
                </div>
                {batchExpanded ? (
                  <ChevronUp className="w-4 h-4 text-blue-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-blue-400" />
                )}
              </button>

              {batchExpanded && (
                <div className="px-4 pb-4 text-sm text-blue-900 space-y-0">
                  {renderMarkdown(batchSummary.summary, searchQuery)}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Extracted text rendered as prose */}
        <div className="space-y-0">
          {renderMarkdown(page.markdown, searchQuery)}
        </div>
      </div>
    </div>
  );
}
