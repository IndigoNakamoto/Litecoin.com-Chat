"use client";

import React, { useState } from "react";
import { BookOpen, Globe, AlertTriangle, ExternalLink, PlayCircle, X } from "lucide-react";
import ArticleModal from "@/components/ArticleModal";

export interface SourceChip {
  payload_id?: string | null;
  slug?: string | null;
  title: string;
  /** Where the chip links: incident-pin URL, the article's canonical origin (sourceUrl), or our reader page. */
  url?: string | null;
  kind?: "youtube" | "external" | "article";
  video_id?: string | null;
  /** Our own public reader page for this article (may equal `url`). */
  reader_url?: string | null;
  updated_at?: string | null;
  last_reviewed_at?: string | null;
  review_interval_days?: number | null;
  stale?: boolean;
  tier?: string;
}

export interface WebSourceChip {
  title: string;
  url: string;
  tier?: "web";
  verified?: false;
}

function formatDate(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function hostLabel(url?: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

const TONES = {
  kb: "border-blue-200 bg-blue-50 text-blue-900 hover:bg-blue-100",
  stale: "border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100",
  web: "border-gray-300 bg-gray-50 text-gray-700 hover:bg-gray-100 border-dashed",
  youtube: "border-red-200 bg-red-50 text-red-900 hover:bg-red-100",
} as const;

const BASE =
  "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs leading-none transition-colors cursor-pointer";

function Chip({
  href,
  onClick,
  tone,
  title,
  children,
}: {
  href?: string | null;
  onClick?: () => void;
  tone: keyof typeof TONES;
  title?: string;
  children: React.ReactNode;
}) {
  const cls = `${BASE} ${TONES[tone]}`;
  if (onClick) {
    return (
      <button type="button" className={cls} title={title} onClick={onClick}>
        {children}
      </button>
    );
  }
  if (href) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={cls} title={title}>
        {children}
        <ExternalLink className="h-3 w-3 shrink-0 opacity-60" aria-hidden />
      </a>
    );
  }
  return (
    <span className={`${cls} cursor-default`} title={title}>
      {children}
    </span>
  );
}

/**
 * Structured provenance under an assistant answer.
 *
 * Knowledge-base chips: a litecoin.com source opens that page; a YouTube source
 * opens an inline player; an editor-authored article opens in an in-chat modal
 * (the chat is embedded on litecoin.com, so readers are never sent elsewhere).
 * A past-review-window doc is labelled "needs review". Web chips are a separate
 * group marked unverified so search grounding is never confused with the
 * Foundation's own content.
 */
export default function SourceChips({
  sources,
  webSources,
}: {
  sources?: SourceChip[];
  webSources?: WebSourceChip[];
}) {
  const kb = sources ?? [];
  const web = webSources ?? [];
  const [openVideo, setOpenVideo] = useState<SourceChip | null>(null);
  const [openArticle, setOpenArticle] = useState<SourceChip | null>(null);
  if (kb.length === 0 && web.length === 0) return null;

  return (
    <div className="mt-4 space-y-2 border-t border-gray-200 pt-3" data-testid="source-chips">
      {kb.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 inline-flex items-center gap-1 text-xs font-medium text-gray-500">
            <BookOpen className="h-3.5 w-3.5" aria-hidden />
            Sources
          </span>
          {kb.map((s) => {
            const updated = formatDate(s.updated_at);
            const reviewed = formatDate(s.last_reviewed_at);
            const isVideo = s.kind === "youtube" && !!s.video_id;
            const isArticle = s.kind === "article" && !!s.payload_id;
            const tone: keyof typeof TONES = isVideo ? "youtube" : s.stale ? "stale" : "kb";
            const host = s.kind === "external" ? hostLabel(s.url) : null;
            const tooltip = [
              s.title,
              isVideo ? "Watch video" : isArticle ? "Read article" : host ? `Open on ${host}` : s.url ? "Open article" : null,
              updated ? `Updated ${updated}` : null,
              reviewed ? `Last reviewed ${reviewed}` : null,
              s.stale ? "Past its review window" : null,
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <Chip
                key={s.payload_id || s.slug || s.title}
                href={isVideo || isArticle ? undefined : s.url}
                onClick={
                  isVideo
                    ? () => setOpenVideo((cur) => (cur?.video_id === s.video_id ? null : s))
                    : isArticle
                      ? () => setOpenArticle(s)
                      : undefined
                }
                tone={tone}
                title={tooltip}
              >
                {isVideo ? <PlayCircle className="h-3.5 w-3.5 shrink-0" aria-hidden /> : null}
                {s.stale && !isVideo ? <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden /> : null}
                <span className="truncate">{s.title}</span>
                {host ? <span className="shrink-0 opacity-60">· {host}</span> : null}
                {s.stale ? <span className="shrink-0 font-medium">· needs review</span> : null}
              </Chip>
            );
          })}
        </div>
      )}

      {openVideo?.video_id && (
        <div className="relative mt-2 overflow-hidden rounded-lg border border-gray-200 bg-black" data-testid="youtube-embed">
          <div className="flex items-center justify-between bg-gray-900 px-3 py-1.5 text-xs text-gray-200">
            <span className="truncate">{openVideo.title}</span>
            <div className="flex items-center gap-3">
              <a
                href={openVideo.url ?? `https://www.youtube.com/watch?v=${openVideo.video_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 hover:text-white"
              >
                Open on YouTube <ExternalLink className="h-3 w-3" aria-hidden />
              </a>
              <button type="button" aria-label="Close video" onClick={() => setOpenVideo(null)} className="hover:text-white">
                <X className="h-3.5 w-3.5" aria-hidden />
              </button>
            </div>
          </div>
          <div className="aspect-video w-full">
            <iframe
              className="h-full w-full"
              src={`https://www.youtube-nocookie.com/embed/${openVideo.video_id}?rel=0`}
              title={openVideo.title}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              referrerPolicy="strict-origin-when-cross-origin"
              allowFullScreen
            />
          </div>
        </div>
      )}

      <ArticleModal
        articleId={openArticle?.payload_id ?? null}
        title={openArticle?.title}
        onClose={() => setOpenArticle(null)}
      />

      {web.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 inline-flex items-center gap-1 text-xs font-medium text-gray-500">
            <Globe className="h-3.5 w-3.5" aria-hidden />
            From the web · unverified
          </span>
          {web.map((w) => (
            <Chip key={w.url} href={w.url} tone="web" title={`${w.title} — not reviewed by the Litecoin Foundation`}>
              <span className="truncate">{w.title}</span>
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}
