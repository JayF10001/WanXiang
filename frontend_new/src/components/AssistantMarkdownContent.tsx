import React from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

type AssistantMarkdownContentProps = {
  content: string;
  className?: string;
};

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="text-lg font-semibold leading-8 text-gray-900">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-semibold leading-8 text-gray-900">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold leading-7 text-gray-800">{children}</h3>,
  h4: ({ children }) => <h4 className="text-sm font-semibold leading-7 text-gray-800">{children}</h4>,
  p: ({ children }) => <p className="text-sm leading-8 text-gray-700">{children}</p>,
  ul: ({ children }) => <ul className="list-disc space-y-2 pl-5 marker:text-blue-500">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-2 pl-5 marker:text-blue-500">{children}</ol>,
  li: ({ children }) => <li className="text-sm leading-7 text-gray-700">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-blue-100 bg-blue-50/60 px-4 py-3 text-sm leading-7 text-gray-700">
      {children}
    </blockquote>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="break-all text-blue-600 underline underline-offset-2 hover:text-blue-700"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="border-gray-200" />,
  table: ({ children }) => (
    <div className="overflow-x-auto rounded-xl border border-gray-200">
      <table className="min-w-full border-collapse bg-white text-left text-sm text-gray-700">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr className="border-t border-gray-200">{children}</tr>,
  th: ({ children }) => <th className="px-3 py-2 font-semibold text-gray-800">{children}</th>,
  td: ({ children }) => <td className="px-3 py-2 align-top">{children}</td>,
  code: ({ inline, children }) => (
    inline ? (
      <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[13px] text-gray-800">{children}</code>
    ) : (
      <code className="block overflow-x-auto whitespace-pre-wrap rounded-xl bg-gray-50 p-4 font-mono text-xs text-gray-700">
        {children}
      </code>
    )
  ),
  pre: ({ children }) => <pre className="overflow-x-auto rounded-xl border border-gray-100 bg-gray-50">{children}</pre>,
};

export function AssistantMarkdownContent({
  content,
  className = '',
}: AssistantMarkdownContentProps) {
  const normalized = String(content || '').replace(/\r\n/g, '\n').trim();
  if (!normalized) {
    return null;
  }

  return (
    <div className={`min-w-0 break-words space-y-4 ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
        skipHtml
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
