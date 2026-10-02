import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Read-only markdown renderer for the public article reader.
 * Mirrors the assistant-message typography in Message.tsx.
 */
export default function ArticleMarkdown({ markdown }: { markdown: string }) {
  return (
    <div className="prose prose-lg max-w-none prose-p:my-6 prose-headings:my-4 leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="font-space-grotesk text-[34px] font-semibold mt-6 mb-4 text-[#222222] border-b border-border pb-2 leading-tight">{children}</h1>,
          h2: ({ children }) => <h2 className="font-space-grotesk text-[26px] font-semibold mt-6 mb-3 text-[#222222] leading-tight">{children}</h2>,
          h3: ({ children }) => <h3 className="font-space-grotesk text-[20px] font-semibold mt-5 mb-2 text-[#222222] leading-tight">{children}</h3>,
          h4: ({ children }) => <h4 className="font-space-grotesk text-lg font-semibold mt-4 mb-2 text-[#222222]">{children}</h4>,
          p: ({ children }) => <p className="my-4 leading-relaxed text-[16px] text-gray-800">{children}</p>,
          ul: ({ children }) => <ul className="my-4 ml-6 list-disc space-y-2">{children}</ul>,
          ol: ({ children }) => <ol className="my-4 ml-6 list-decimal space-y-2">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed text-gray-800">{children}</li>,
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            return isInline ? (
              <code className="bg-muted px-1.5 py-0.5 rounded text-base font-mono text-gray-800" {...props}>
                {children}
              </code>
            ) : (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="bg-muted border border-border rounded-lg p-4 overflow-x-auto my-4 text-base font-mono leading-relaxed">{children}</pre>
          ),
          a: ({ href, children }) => (
            <a href={href} className="text-blue-500 hover:text-blue-600 underline underline-offset-2 transition-colors" target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          blockquote: ({ children }) => <blockquote className="border-l-4 border-blue-500/30 pl-4 italic my-4 text-gray-600">{children}</blockquote>,
          strong: ({ children }) => <strong className="font-semibold text-gray-800">{children}</strong>,
          hr: () => <hr className="border-border my-6" />,
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto">
              <table className="w-full border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-muted">{children}</thead>,
          th: ({ children }) => <th className="border border-border px-4 py-2 text-left font-semibold text-gray-800">{children}</th>,
          td: ({ children }) => <td className="border border-border px-4 py-2 text-gray-800">{children}</td>,
          img: ({ src, alt }) => <img src={src} alt={alt} className="rounded-lg my-4 max-w-full" />,
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
