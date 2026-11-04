'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

// Custom markdown components for the Synthèse IA dialog — renders LLM output
// with bold/italic/headings/lists. Note: react-markdown follows CommonMark,
// so `__text__` and `**text**` both produce <strong>, and `*text*`/`_text_`
// produce <em>. True underline is not part of CommonMark — we render <u>
// tags via the `u` component (LLM must emit raw <u>...</u> for underline,
// which is preserved as text and rendered through the override below).
const SYNTHESE_MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <div className="text-indigo-700 font-semibold text-base mt-3 mb-1">{children}</div>,
  h2: ({ children }) => <div className="text-indigo-700 font-semibold mt-3 mb-1">{children}</div>,
  h3: ({ children }) => <div className="text-indigo-600 font-semibold mt-2 mb-1">{children}</div>,
  h4: ({ children }) => <div className="text-slate-700 font-semibold mt-2 mb-1">{children}</div>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  em: ({ children }) => <em className="italic text-slate-800">{children}</em>,
  ul: ({ children }) => <ul className="list-disc list-inside space-y-1 my-1 text-slate-700">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 my-1 text-slate-700">{children}</ol>,
  li: ({ children }) => <li className="text-slate-700">{children}</li>,
  p: ({ children }) => <p className="my-1 text-slate-700 leading-relaxed">{children}</p>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-600 underline hover:text-indigo-800">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="font-mono text-xs bg-slate-100 text-slate-800 px-1 py-0.5 rounded">{children}</code>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-indigo-300 pl-3 italic text-slate-600 my-2">{children}</blockquote>
  ),
};

/** AI prose rendered with the cockpit typography (bold, lists, links; no raw HTML). */
export default function MarkdownText({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed text-slate-700">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={SYNTHESE_MARKDOWN_COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
