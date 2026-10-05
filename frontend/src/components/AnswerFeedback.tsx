"use client";

import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, Check, AlertCircle } from "lucide-react";
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
 *
 * The verdict is recorded the moment a thumb is clicked. For a thumbs-down the
 * reason chips are an optional refinement: picking one re-posts the same
 * request (the backend upserts per request + fingerprint), so the signal is
 * kept even if the reader walks away. Success is only shown after the server
 * actually accepted the record.
 */
export default function AnswerFeedback({ requestId, sourcePayloadIds }: AnswerFeedbackProps) {
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [recorded, setRecorded] = useState(false);
  const [reasonRecorded, setReasonRecorded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const post = async (v: Verdict, r: string | null): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      try {
        const fp = await getFingerprint();
        if (fp) headers["X-Fingerprint"] = fp;
      } catch {
        /* fingerprint is best-effort */
      }
      const res = await fetch(apiUrl("/api/v1/chat/feedback"), {
        method: "POST",
        headers,
        body: JSON.stringify({
          request_id: requestId,
          verdict: v,
          reason: r,
          source_payload_ids: sourcePayloadIds,
        }),
      });
      if (!res.ok) {
        setError(res.status === 429 ? "Too many requests — try again in a minute." : "Couldn't record your feedback. Please try again.");
        return false;
      }
      return true;
    } catch (e) {
      console.debug("feedback post failed", e);
      setError("Couldn't record your feedback. Please try again.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const onThumb = async (v: Verdict) => {
    if (busy || recorded) return;
    setVerdict(v);
    const ok = await post(v, null);
    if (ok) setRecorded(true);
    else setVerdict(null);
  };

  const onReason = async (r: string) => {
    if (busy || reasonRecorded || verdict !== "down") return;
    setReason(r);
    const ok = await post("down", r);
    if (ok) setReasonRecorded(true);
    else setReason(null);
  };

  const retry = () => {
    if (verdict === "down" && recorded && reason) void onReason(reason);
    else if (verdict) void onThumb(verdict);
  };

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500" data-testid="answer-feedback">
      {recorded ? (
        <span className="inline-flex items-center gap-1.5" data-testid="feedback-thanks">
          <Check className="h-3.5 w-3.5 text-green-600" aria-hidden />
          {verdict === "up" ? "Thanks — glad it helped." : "Thanks — your feedback was recorded."}
        </span>
      ) : (
        <>
          <span>Was this helpful?</span>
          <button
            type="button"
            aria-label="Helpful"
            aria-pressed={verdict === "up"}
            onClick={() => void onThumb("up")}
            disabled={busy}
            className={`rounded-full border p-1.5 transition-colors hover:bg-green-50 disabled:opacity-60 ${
              verdict === "up" ? "border-green-400 text-green-700" : "border-gray-200 text-gray-500"
            }`}
          >
            <ThumbsUp className="h-3.5 w-3.5" aria-hidden />
          </button>
          <button
            type="button"
            aria-label="Not helpful"
            aria-pressed={verdict === "down"}
            onClick={() => void onThumb("down")}
            disabled={busy}
            className={`rounded-full border p-1.5 transition-colors hover:bg-red-50 disabled:opacity-60 ${
              verdict === "down" ? "border-red-400 text-red-700" : "border-gray-200 text-gray-500"
            }`}
          >
            <ThumbsDown className="h-3.5 w-3.5" aria-hidden />
          </button>
        </>
      )}

      {recorded && verdict === "down" && !reasonRecorded && (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="feedback-reasons">
          <span className="text-gray-400">What went wrong?</span>
          {REASONS.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => void onReason(r.id)}
              disabled={busy}
              className={`rounded-full border px-2 py-0.5 transition-colors disabled:opacity-60 ${
                reason === r.id ? "border-gray-700 bg-gray-800 text-white" : "border-gray-300 hover:bg-gray-100"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
      {recorded && verdict === "down" && reasonRecorded && (
        <span className="text-gray-400" data-testid="feedback-reason-thanks">
          Noted: {REASONS.find((r) => r.id === reason)?.label ?? reason}.
        </span>
      )}

      {error && (
        <span className="inline-flex items-center gap-1 text-red-600" role="alert" data-testid="feedback-error">
          <AlertCircle className="h-3.5 w-3.5" aria-hidden />
          {error}
          <button type="button" onClick={retry} disabled={busy} className="underline underline-offset-2 hover:text-red-800 disabled:opacity-60">
            Retry
          </button>
        </span>
      )}
    </div>
  );
}
