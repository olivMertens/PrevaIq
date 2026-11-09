'use client';

import { useMemo } from 'react';
import { ExternalLink } from 'lucide-react';
import { useTranslations } from 'next-intl';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { RAGCitation } from './types';
import { citationReferenceMap, policyReferencePlugin } from './policyReferences';

const EMPTY_CITATIONS: RAGCitation[] = [];
const formatting: Components = {
  h1: ({children}) => <h1 className="mb-2 mt-3 text-base font-bold text-teal-900 first:mt-0">{children}</h1>,
  h2: ({children}) => <h2 className="mb-1.5 mt-3 border-b border-teal-200 pb-1 text-sm font-bold text-teal-900 first:mt-0">{children}</h2>,
  h3: ({children}) => <h3 className="mb-1 mt-2 text-sm font-semibold text-teal-800 first:mt-0">{children}</h3>,
  h4: ({children}) => <h4 className="mb-1 mt-2 text-xs font-semibold text-slate-800">{children}</h4>,
  p: ({children}) => <p className="mb-2 text-sm leading-relaxed text-slate-700 last:mb-0">{children}</p>,
  strong: ({children}) => <strong className="font-bold text-teal-900">{children}</strong>,
  em: ({children}) => <em className="italic text-slate-700">{children}</em>,
  ul: ({children}) => <ul className="mb-2 ml-4 list-outside list-disc space-y-1 text-sm">{children}</ul>,
  ol: ({children}) => <ol className="mb-2 ml-4 list-outside list-decimal space-y-1 text-sm">{children}</ol>,
  li: ({children}) => <li className="leading-relaxed text-slate-700">{children}</li>,
  hr: () => <hr className="my-3 border-slate-200" />,
  blockquote: ({children}) => <blockquote className="my-2 rounded-r-lg border-l-4 border-teal-400 bg-teal-50/60 px-3 py-2 text-sm italic text-slate-700">{children}</blockquote>,
  table: ({children}) => <div className="my-2 overflow-x-auto rounded-lg border border-slate-200"><table className="min-w-full text-xs">{children}</table></div>,
  thead: ({children}) => <thead className="bg-slate-100">{children}</thead>,
  th: ({children}) => <th className="border-b border-slate-200 px-2 py-1.5 text-left font-semibold text-slate-800">{children}</th>,
  td: ({children}) => <td className="border-b border-slate-100 px-2 py-1.5 text-slate-700">{children}</td>,
  code: ({className, children}) => <code className={className
    ? `block overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs ${className}`
    : 'rounded bg-indigo-50 px-1 py-0.5 font-mono text-xs text-indigo-800'}>{children}</code>,
};

export default function ChatMarkdown({
  content, citations = EMPTY_CITATIONS, onPolicyClick,
}: {content: string; citations?: RAGCitation[]; onPolicyClick?: (policyId: string) => void}) {
  const t = useTranslations('chat');
  const policyIds = new Set(citationReferenceMap(citations).values());
  const referencePlugin = useMemo(() => policyReferencePlugin(citations), [citations]);
  return (
    <div className="min-w-0 break-words [overflow-wrap:anywhere]">
      <ReactMarkdown remarkPlugins={[remarkGfm, referencePlugin]} components={{
        ...formatting,
        a: ({href, children}) => {
          const id = href?.startsWith('#policy/') ? href.slice('#policy/'.length) : null;
          if (id && policyIds.has(id) && onPolicyClick) return (
            <button type="button" onClick={() => onPolicyClick(id)} title={t('clickToViewPolicy')}
              className="inline rounded-sm font-semibold text-indigo-700 underline decoration-2 underline-offset-2 hover:text-indigo-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600">
              {children}
            </button>
          );
          if (!href || id) return <span>{children}</span>;
          return <a href={href} target="_blank" rel="noopener noreferrer"
            className="font-medium text-indigo-700 underline underline-offset-2 hover:text-indigo-900">
            {children}<ExternalLink className="ml-0.5 inline h-3 w-3" aria-hidden />
          </a>;
        },
      }}>{content}</ReactMarkdown>
    </div>
  );
}
