"use client";

import React, { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

interface CopyAnswerButtonProps {
  /** Raw answer markdown; copied as-is so lists and headings survive a paste. */
  text: string;
}

/** Small "Copy" affordance shown under every assistant answer. */
export default function CopyAnswerButton({ text }: CopyAnswerButtonProps) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const onCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        // Fallback for insecure contexts / older browsers.
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      console.debug("copy failed", e);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void onCopy()}
      aria-label={copied ? "Copied" : "Copy answer"}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs transition-colors ${
        copied
          ? "border-green-400 text-green-700"
          : "border-gray-200 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
      }`}
      data-testid="copy-answer"
    >
      {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
