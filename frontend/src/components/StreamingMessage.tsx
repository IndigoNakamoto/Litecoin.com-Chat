import React, { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeMarkdown } from "@/lib/markdownUtils";

interface StreamingMessageProps {
  content: string;
  status: "thinking" | "streaming" | "complete" | "error";
  isStreamActive: boolean;
}

const StreamingMessage: React.FC<StreamingMessageProps> = ({
  content,
  status,
  isStreamActive
}) => {
  // Normalize markdown to fix LLM output issues (missing newlines before headings)
  const normalizedContent = useMemo(() => normalizeMarkdown(content), [content]);

  const getStatusColor = () => {
    switch (status) {
      case "thinking":
        return "text-blue-500";
      case "streaming":
        return "text-blue-500";
      case "error":
        return "text-destructive";
      default:
        return "text-gray-600";
    }
  };

  return (
    <div className={`w-full transition-all duration-300 ${status === "streaming" && isStreamActive ? "animate-stream-pulse" : ""}`}>
      {/* Status indicator */}
      {status !== "complete" && (
        <div className={`text-sm ${getStatusColor()} flex items-center gap-3 mb-3 transition-opacity duration-300`}>
          <div className="flex gap-1.5 items-center">
            <div className="w-2 h-2 bg-current rounded-full animate-bounce [animation-delay:-0.3s]"></div>
            <div className="w-2 h-2 bg-current rounded-full animate-bounce [animation-delay:-0.15s]"></div>
            <div className="w-2 h-2 bg-current rounded-full animate-bounce"></div>
          </div>
        </div>
      )}

      {/* Message content */}
      <div className="prose prose-lg max-w-none prose-p:my-6 prose-headings:my-4 leading-relaxed relative">
        <div className="animate-fade-in">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h1 className="font-space-grotesk text-[39px] font-semibold mt-6 mb-4 text-[#222222] border-b border-border pb-2 leading-tight">{children}</h1>,
              h2: ({ children }) => <h2 className="font-space-grotesk text-[30px] font-semibold mt-5 mb-3 text-[#222222] leading-tight">{children}</h2>,
              h3: ({ children }) => <h3 className="font-space-grotesk text-[20px] font-semibold mt-4 mb-2 text-[#222222] leading-tight">{children}</h3>,
              h4: ({ children }) => <h4 className="font-space-grotesk text-lg font-semibold mt-3 mb-2 text-[#222222]">{children}</h4>,
              h5: ({ children }) => <h5 className="font-space-grotesk text-base font-semibold mt-2 mb-1 text-[#222222]">{children}</h5>,
              h6: ({ children }) => <h6 className="font-space-grotesk text-base font-medium mt-2 mb-1 text-gray-600">{children}</h6>,
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
                <pre className="bg-muted border border-border rounded-lg p-4 overflow-x-auto my-4 text-base font-mono leading-relaxed">
                  {children}
                </pre>
              ),
              a: ({ href, children }) => (
                <a href={href} className="text-blue-500 hover:text-blue-600 underline underline-offset-2 transition-colors" target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-4 border-blue-500/30 pl-4 italic my-4 text-gray-600">
                  {children}
                </blockquote>
              ),
              strong: ({ children }) => <strong className="font-semibold text-gray-800">{children}</strong>,
              em: ({ children }) => <em className="italic">{children}</em>,
              hr: () => <hr className="border-border my-6" />,
              table: ({ children }) => (
                <div className="my-4 overflow-x-auto">
                  <table className="w-full border-collapse">
                    {children}
                  </table>
                </div>
              ),
              thead: ({ children }) => <thead className="bg-muted">{children}</thead>,
              th: ({ children }) => <th className="border border-border px-4 py-2 text-left font-semibold text-gray-800">{children}</th>,
              td: ({ children }) => <td className="border border-border px-4 py-2 text-gray-800">{children}</td>,
              tr: ({ children, ...props }) => <tr className="even:bg-muted/50" {...props}>{children}</tr>,
              img: ({ src, alt }) => <img src={src} alt={alt} className="rounded-lg my-4 max-w-full" />,
            }}
          >
            {normalizedContent}
          </ReactMarkdown>
        </div>
      </div>

    </div>
  );
};

export default StreamingMessage;
