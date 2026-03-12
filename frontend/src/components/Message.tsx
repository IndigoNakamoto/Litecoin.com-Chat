import { Button } from "@/components/ui/button";
import FollowUpQuestions from "@/components/FollowUpQuestions";
import React, { useState, useEffect, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeMarkdown } from "@/lib/markdownUtils";

interface MessageProps {
  role: "user" | "assistant";
  content: string;
  followUpQuestions?: string[];
  isGrounded?: boolean;
  messageId?: string;
  retryInfo?: {
    retryAfterSeconds: number;
    banExpiresAt?: number;
    violationCount?: number;
    errorType: string;
    originalMessage?: string;
  };
  onRetry?: () => void;
  onFollowUpClick?: (question: string) => void;
}

const Message: React.FC<MessageProps> = ({
  role,
  content,
  followUpQuestions,
  isGrounded,
  messageId,
  retryInfo,
  onRetry,
  onFollowUpClick,
}) => {
  const isUser = role === "user";
  const messageRef = React.useRef<HTMLDivElement>(null);
  
  // Normalize markdown to fix LLM output issues (missing newlines before headings)
  const normalizedContent = useMemo(() => normalizeMarkdown(content), [content]);
  
  // Countdown timer for retry
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  
  // Debug logging for retry info
  useEffect(() => {
    if (isUser) {
      console.debug("Message component received props:", {
        messageId,
        role,
        hasRetryInfo: !!retryInfo,
        hasOnRetry: !!onRetry,
        retryInfo,
        onRetryDefined: typeof onRetry === 'function',
      });
      
      if (retryInfo && !onRetry) {
        console.warn("Retry info present but onRetry is missing:", {
          messageId,
          retryInfo,
          hasOriginalMessage: !!retryInfo.originalMessage,
        });
      }
      
      if (retryInfo && onRetry) {
        console.debug("Retry button should be visible:", {
          messageId,
          retryInfo,
          remainingSeconds,
          canRetry,
        });
      }
    }
  }, [messageId, role, retryInfo, onRetry, isUser, remainingSeconds, canRetry]);
  
  useEffect(() => {
    if (!retryInfo || !isUser) {
      if (isUser && !retryInfo) {
        console.debug("Message component: retryInfo not present for user message:", messageId);
      }
      if (isUser && retryInfo && !isUser) {
        console.debug("Message component: retryInfo present but not a user message:", messageId);
      }
      return;
    }
    
    // Calculate initial remaining seconds
    const banExpiresAt = retryInfo.banExpiresAt;
    const retryAfterSeconds = retryInfo.retryAfterSeconds || 0;
    
    console.debug("Message retry info:", { banExpiresAt, retryAfterSeconds, retryInfo });
    
    let initialRemaining: number;
    if (banExpiresAt) {
      // Calculate from ban expiration timestamp (Unix timestamp in seconds)
      const now = Math.floor(Date.now() / 1000);
      const banExpires = typeof banExpiresAt === 'number' ? banExpiresAt : parseInt(String(banExpiresAt), 10);
      initialRemaining = Math.max(0, banExpires - now);
      
      // If banExpiresAt calculation gives 0 or negative, fall back to retryAfterSeconds
      if (initialRemaining <= 0 && retryAfterSeconds > 0) {
        console.debug("banExpiresAt calculation resulted in 0 or negative, using retryAfterSeconds:", retryAfterSeconds);
        initialRemaining = retryAfterSeconds;
      }
    } else {
      // Use retryAfterSeconds directly
      initialRemaining = retryAfterSeconds;
    }
    
    console.debug("Calculated initial remaining seconds:", initialRemaining);
    
    setRemainingSeconds(initialRemaining);
    setCanRetry(initialRemaining <= 0);
    
    if (initialRemaining > 0) {
      // Start countdown
      const interval = setInterval(() => {
        setRemainingSeconds((prev) => {
          if (prev === null || prev <= 1) {
            setCanRetry(true);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      
      return () => clearInterval(interval);
    }
  }, [retryInfo, isUser, messageId]);
  
  const formatTime = (seconds: number): string => {
    if (seconds >= 60) {
      const minutes = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `${minutes}m ${secs}s`;
    }
    return `${seconds}s`;
  };

  if (!isUser) {
    // AI messages take full width
    return (
      <div ref={messageRef} id={messageId} className="w-full">
        <div className="prose prose-lg max-w-none prose-p:my-6 prose-headings:my-4 leading-relaxed">
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
        {isGrounded && (
          <div className="flex items-center gap-1.5 mt-4 pt-3 border-t border-gray-200 text-xs text-gray-500">
            <svg className="w-3.5 h-3.5 text-blue-500 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418" />
            </svg>
            <span>This answer includes information supplemented from web search</span>
          </div>
        )}
        {followUpQuestions && followUpQuestions.length > 0 && onFollowUpClick && (
          <FollowUpQuestions
            questions={followUpQuestions}
            onQuestionClick={onFollowUpClick}
          />
        )}
      </div>
    );
  }

  // User messages remain in chat bubble format
  return (
    <div ref={messageRef} id={messageId} className="flex items-start gap-4 justify-end">
      <div className="flex flex-col gap-2 p-5 my-8 rounded-tl-3xl rounded-br-3xl rounded-tr-none rounded-bl-none max-w-[70%] bg-[#222222] text-white">
        <div className="prose prose-lg max-w-none prose-p:my-6 prose-headings:my-4 leading-relaxed">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h1 className="font-space-grotesk text-[39px] font-semibold mt-6 mb-4 text-white border-b border-white/20 pb-2 leading-tight">{children}</h1>,
              h2: ({ children }) => <h2 className="font-space-grotesk text-[30px] font-semibold mt-5 mb-3 text-white leading-tight">{children}</h2>,
              h3: ({ children }) => <h3 className="font-space-grotesk text-[20px] font-semibold mt-4 mb-2 text-white leading-tight">{children}</h3>,
              h4: ({ children }) => <h4 className="font-space-grotesk text-lg font-semibold mt-3 mb-2 text-white">{children}</h4>,
              h5: ({ children }) => <h5 className="font-space-grotesk text-base font-semibold mt-2 mb-1 text-white">{children}</h5>,
              h6: ({ children }) => <h6 className="font-space-grotesk text-base font-medium mt-2 mb-1 text-white/80">{children}</h6>,
              p: ({ children }) => <p className="my-4 leading-relaxed text-[16px] text-white">{children}</p>,
              ul: ({ children }) => <ul className="my-4 ml-6 list-disc space-y-2">{children}</ul>,
              ol: ({ children }) => <ol className="my-4 ml-6 list-decimal space-y-2">{children}</ol>,
              li: ({ children }) => <li className="leading-relaxed text-white">{children}</li>,
              code: ({ className, children, ...props }) => {
                const isInline = !className;
                return isInline ? (
                  <code className="bg-white/20 px-1.5 py-0.5 rounded text-base font-mono text-white" {...props}>
                    {children}
                  </code>
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              },
              pre: ({ children }) => (
                <pre className="bg-white/10 border border-white/20 rounded-lg p-4 overflow-x-auto my-4 text-base font-mono leading-relaxed">
                  {children}
                </pre>
              ),
              a: ({ href, children }) => (
                <a href={href} className="text-white/90 hover:text-white underline underline-offset-2 transition-colors" target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-4 border-white/30 pl-4 italic my-4 text-white/80">
                  {children}
                </blockquote>
              ),
              strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
              em: ({ children }) => <em className="italic">{children}</em>,
              hr: () => <hr className="border-white/20 my-6" />,
              table: ({ children }) => (
                <div className="my-4 overflow-x-auto">
                  <table className="w-full border-collapse">
                    {children}
                  </table>
                </div>
              ),
              thead: ({ children }) => <thead className="bg-white/10">{children}</thead>,
              th: ({ children }) => <th className="border border-white/20 px-4 py-2 text-left font-semibold text-white">{children}</th>,
              td: ({ children }) => <td className="border border-white/20 px-4 py-2 text-white">{children}</td>,
              tr: ({ children, ...props }) => <tr className="even:bg-white/5" {...props}>{children}</tr>,
              img: ({ src, alt }) => <img src={src} alt={alt} className="rounded-lg my-4 max-w-full" />,
            }}
          >
            {normalizedContent}
          </ReactMarkdown>
        </div>
        {retryInfo && onRetry && (
          <div className="mt-3 pt-3 border-t border-white/20">
            <div className="flex flex-col gap-2">
              <p className="text-sm text-white/80">
                {retryInfo.errorType === "too_many_challenges" && (
                  <>
                    Too many requests. Please wait before trying again.
                  </>
                )}
                {retryInfo.errorType === "cost_throttled" && (
                  <>
                    High usage detected. Please wait before trying again.
                  </>
                )}
              </p>
              {remainingSeconds !== null && remainingSeconds > 0 && (
                <p className="text-xs text-white/60">
                  Please wait {formatTime(remainingSeconds)} before retrying.
                </p>
              )}
              <Button
                onClick={onRetry}
                disabled={!canRetry}
                className="w-full bg-white/10 hover:bg-white/20 text-white border border-white/20 disabled:opacity-50 disabled:cursor-not-allowed"
                size="sm"
              >
                {canRetry ? (
                  <>🔄 Retry</>
                ) : (
                  <>⏱️ Wait {remainingSeconds !== null ? formatTime(remainingSeconds) : ""}</>
                )}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Message;
