"use client";

import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, Check } from "lucide-react";
import { getFingerprint } from "@/lib/utils/fingerprint";
import { apiUrl } from "@/lib/apiBase";

type Verdict = "up" | "down";

interface AnswerFeedbackProps {
  requestId: string;
  sourcePayloadIds: string[];
}

const REASONS: Array<{ id: string; label: string }> = [
  { id: "outdated", label: "Out of date" },
  { id: "incorrect", label: "Incorrect" },
  { id: "incomplete", label: "Missing something" },
  { id: "off_topic", label: "Didn't answer the question" },
];

/**
 * Thumbs up/down under a cited answer.
 *
 * A thumbs-down is filed against the cited source documents (`sourcePayloadIds`),
 * not against the model: most "wrong answers" are stale or missing chunks.
 */
export default function AnswerFeedback({ requestId, sourcePayloadIds }: AnswerFeedbackProps) {
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async (v: Verdict, r: string | null) => {
    setBusy(true);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      try {
        const fp = await getFingerprint();
        if (fp) headers["X-Fingerprint"] = fp;
      } catch {
        /* fingerprint is best-effort */
      }
      await fetch(apiUrl("/api/v1/chat/feedback"), {
        method: "POST",
        headers,
        body: JSON.stringify({
          request_id: requestId,
          verdict: v,
          reason: r,
          source_payload_ids: sourcePayloadIds,
        }),
      });
    } catch (e) {
      console.debug("feedback post failed", e);
    } finally {
      setBusy(false);
      setSubmitted(true);
    }
  };

  const onThumb = (v: Verdict) => {
    if (submitted || busy) return;
    setVerdict(v);
    if (v === "up") void send("up", null);
  };

  if (submitted) {
    return (
      <div className="mt-3 inline-flex items-center gap-1.5 text-xs text-gray-500" data-testid="feedback-thanks">
        <Check className="h-3.5 w-3.5 text-green-600" aria-hidden />
        Thanks — your feedback was recorded.
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-500" data-testid="answer-feedback">
      <span>Was this helpful?</span>
      <button
        type="button"
        aria-label="Helpful"
        aria-pressed={verdict === "up"}
        onClick={() => onThumb("up")}
        disabled={busy}
        className={`rounded-full border p-1.5 transition-colors hover:bg-green-50 ${
          verdict === "up" ? "border-green-400 text-green-700" : "border-gray-200 text-gray-500"
        }`}
      >
        <ThumbsUp className="h-3.5 w-3.5" aria-hidden />
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        aria-pressed={verdict === "down"}
        onClick={() => onThumb("down")}
        disabled={busy}
        className={`rounded-full border p-1.5 transition-colors hover:bg-red-50 ${
          verdict === "down" ? "border-red-400 text-red-700" : "border-gray-200 text-gray-500"
        }`}
      >
        <ThumbsDown className="h-3.5 w-3.5" aria-hidden />
      </button>
      {verdict === "down" && (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="feedback-reasons">
          {REASONS.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setReason(r.id)}
              className={`rounded-full border px-2 py-0.5 transition-colors ${
                reason === r.id ? "border-gray-700 bg-gray-800 text-white" : "border-gray-300 hover:bg-gray-100"
              }`}
            >
              {r.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => void send("down", reason)}
            disabled={busy}
            className="rounded-full bg-gray-900 px-2.5 py-0.5 font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
