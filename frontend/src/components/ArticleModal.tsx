"use client";

import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X, ExternalLink, Clock, AlertTriangle } from "lucide-react";
import ArticleMarkdown from "@/components/ArticleMarkdown";
import { apiUrl } from "@/lib/apiBase";

interface PublicArticle {
  id: string;
  title: string;
  markdown: string;
  source_url?: string | null;
  source_tier?: string | null;
  updated_at?: string | null;
  last_reviewed_at?: string | null;
}

interface ArticleModalProps {
  articleId: string | null;
  title?: string;
  onClose: () => void;
}

function fmt(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

function stripLeadingTitle(markdown: string, title: string): string {
  const lines = markdown.split("\n");
  const first = lines.findIndex((l) => l.trim() !== "");
  if (first >= 0 && /^#\s+/.test(lines[first]) && lines[first].replace(/^#\s+/, "").trim() === title.trim()) {
    return lines.slice(first + 1).join("\n").trimStart();
  }
  return markdown;
}

/**
 * In-chat reader for a cited knowledge-base article.
 *
 * Fetches `/api/v1/articles/{id}` through the chat's own origin (rewritten to
 * the backend) so a reader embedded on litecoin.com never leaves the page.
 */
export default function ArticleModal({ articleId, title, onClose }: ArticleModalProps) {
  const [article, setArticle] = useState<PublicArticle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!articleId) return;
    let cancelled = false;
    setArticle(null);
    setError(null);
    setLoading(true);
    fetch(apiUrl(`/api/v1/articles/${encodeURIComponent(articleId)}`), { headers: { Accept: "application/json" } })
      .then(async (r) => {
        if (!r.ok) {
          throw new Error(r.status === 404 ? "This article is not published or no longer exists." : "Could not load the article right now.");
        }
        return (await r.json()) as PublicArticle;
      })
      .then((a) => {
        if (!cancelled) setArticle(a);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [articleId]);

  useEffect(() => {
    if (!articleId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [articleId, onClose]);

  if (!articleId || typeof document === "undefined") return null;

  const updated = fmt(article?.updated_at);
  const reviewed = fmt(article?.last_reviewed_at);
  const sourceHost = (() => {
    try {
      return article?.source_url ? new URL(article.source_url).hostname.replace(/^www\./, "") : null;
    } catch {
      return null;
    }
  })();

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-6"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      data-testid="article-modal"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="article-modal-title"
        className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl outline-none sm:rounded-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-5 py-4">
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
              {article?.source_tier === "pinned" ? "Reference document" : "Litecoin Knowledge Hub"}
            </div>
            <h2 id="article-modal-title" className="font-space-grotesk mt-0.5 text-xl font-semibold leading-tight text-[#222222]">
              {article?.title || title || "Article"}
            </h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
              {updated ? (
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" aria-hidden />
                  Updated {updated}
                </span>
              ) : null}
              {reviewed ? <span>Last reviewed {reviewed}</span> : null}
              {article?.source_url ? (
                <a
                  href={article.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800"
                >
                  Original source{sourceHost ? ` (${sourceHost})` : ""}
                  <ExternalLink className="h-3 w-3" aria-hidden />
                </a>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close article"
            className="rounded-full p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-4 sm:px-7">
          {loading && <div className="py-10 text-center text-sm text-gray-500">Loading article…</div>}
          {error && (
            <div className="my-6 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <div>
                <div className="font-medium">Article not available</div>
                <div className="mt-0.5">{error}</div>
              </div>
            </div>
          )}
          {article && <ArticleMarkdown markdown={stripLeadingTitle(article.markdown, article.title)} />}
        </div>

        <div className="border-t border-gray-200 px-5 py-3 text-xs text-gray-500">
          From the sourced knowledge base behind Litecoin Chat. Spotted something out of date? Use the thumbs-down on the answer that cited it.
        </div>
      </div>
    </div>,
    document.body,
  );
}
