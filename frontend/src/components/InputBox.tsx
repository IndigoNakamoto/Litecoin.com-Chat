import React, { useState, useRef, useEffect } from "react";
import { Send, Sparkles, AlertCircle } from "lucide-react";

interface InputBoxProps {
  onSendMessage: (message: string) => void;
  isLoading: boolean;
  showConversationActions?: boolean;
  onClearConversation?: () => void;
}

const MAX_QUERY_LENGTH = 400;

const InputBox: React.FC<InputBoxProps> = ({
  onSendMessage,
  isLoading,
  showConversationActions = false,
  onClearConversation,
}) => {
  const [input, setInput] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [showWarning, setShowWarning] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleSend = () => {
    if (input.trim() && !isLoading) {
      // Check if message exceeds limit
      if (input.length > MAX_QUERY_LENGTH) {
        setShowWarning(true);
        // Add shake animation
        if (containerRef.current) {
          containerRef.current.classList.add("animate-shake");
          setTimeout(() => {
            containerRef.current?.classList.remove("animate-shake");
          }, 500);
        }
        // Clear warning after 3 seconds
        setTimeout(() => {
          setShowWarning(false);
        }, 3000);
        return;
      }
      onSendMessage(input);
      setInput("");
      setShowWarning(false);
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  };

  const handleKeyPress = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !isLoading) {
      event.preventDefault();
      handleSend();
    }
  };

  // Clear warning when user starts typing
  useEffect(() => {
    if (showWarning && input.length <= MAX_QUERY_LENGTH) {
      setShowWarning(false);
    }
  }, [input, showWarning]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const isOverLimit = input.length > MAX_QUERY_LENGTH;

  return (
    <div className="shrink-0 bg-background">
      <div className="mx-auto max-w-4xl px-4 py-4">
        {showConversationActions && onClearConversation && (
          <div className="mb-2 flex items-center justify-between px-2">
            <div className="flex-1" />
            <button
              type="button"
              onClick={onClearConversation}
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Clear conversation
            </button>
          </div>
        )}
        <div 
          ref={containerRef}
          className={`relative flex items-end gap-3 bg-white/85 rounded-2xl border text-foreground shadow-lg shadow-black/20 transition-all ${
            showWarning || isOverLimit
              ? 'border-red-500 focus-within:border-red-500 focus-within:shadow-red-500/20'
              : 'border-border focus-within:border-primary/60 focus-within:shadow-xl focus-within:shadow-primary/10'
          }`}
          style={{
            backdropFilter: 'blur(4px)',
            WebkitBackdropFilter: 'blur(4px)',
          }}
        >
          {/* Litecoin logo/sparkles on focus */}
          {isFocused && (
            <div className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none">
              <Sparkles className="h-4 w-4 text-primary animate-sparkle" />
            </div>
          )}
          <textarea
            ref={textareaRef}
            placeholder="Ask anything about Litecoin..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyPress}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            disabled={isLoading}
            rows={1}
            className={`flex-1 resize-none border-0 bg-transparent py-3.5 text-[16px] leading-7 text-foreground placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 min-h-[56px] max-h-[200px] overflow-y-auto transition-all ${
              isFocused ? 'pl-12 pr-4' : 'px-4'
            }`}
            style={{
              scrollbarWidth: "thin",
              scrollbarColor: "var(--muted) transparent",
            }}
          />
          <div className="flex items-end pb-2 pr-2">
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="h-10 w-10 rounded-xl bg-gradient-to-r from-primary to-primary/80 border border-primary/20 text-white shadow-lg hover:shadow-xl hover:shadow-primary/10 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300 shrink-0 hover:scale-105 active:scale-95 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 flex items-center justify-center"
              aria-label="Send message"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
        {showWarning && (
          <div className="mt-2 mx-4 px-3 py-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-2 animate-fade-in">
            <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-700 dark:text-red-400">
                Message is too long
              </p>
              <p className="text-xs text-red-600 dark:text-red-500 mt-0.5">
                Maximum length is {MAX_QUERY_LENGTH} characters. Your message is {input.length} characters.
              </p>
            </div>
          </div>
        )}
        <div className={`mt-2 flex justify-between items-center px-4 transition-opacity ${showWarning ? 'opacity-60' : ''}`}>
          <p className="text-sm text-muted-foreground">
            Press Enter to send, Shift+Enter for new line
          </p>
          <p className={`text-sm font-medium ${
            input.length > MAX_QUERY_LENGTH 
              ? 'text-red-500' 
              : input.length > MAX_QUERY_LENGTH * 0.9 
                ? 'text-yellow-500' 
                : 'text-muted-foreground'
          }`}>
            {input.length}/{MAX_QUERY_LENGTH}
          </p>
        </div>
      </div>
    </div>
  );
};

export default InputBox;
