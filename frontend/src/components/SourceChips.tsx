"use client";

import React from "react";
import { BookOpen, Globe, AlertTriangle, ExternalLink } from "lucide-react";

export interface SourceChip {
  payload_id?: string | null;
  slug?: string | null;
  title: string;
  url?: string | null;
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

function ChipShell({
  href,
  children,
  tone,
  title,
}: {
  href?: string | null;
  children: React.ReactNode;
  tone: "kb" | "web" | "stale";
  title?: string;
}) {
  const base =
    "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs leading-none transition-colors";
  const tones: Record<typeof tone, string> = {
    kb: "border-blue-200 bg-blue-50 text-blue-900 hover:bg-blue-100",
    stale: "border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100",
    web: "border-gray-300 bg-gray-50 text-gray-700 hover:bg-gray-100 border-dashed",
  };
  const cls = `${base} ${tones[tone]}`;
  if (href) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={cls} title={title}>
        {children}
        <ExternalLink className="h-3 w-3 shrink-0 opacity-60" aria-hidden />
      </a>
    );
  }
  return (
    <span className={cls} title={title}>
      {children}
    </span>
  );
}

/**
 * Structured provenance under an assistant answer.
 *
 * Knowledge-base chips carry title, reader link and CMS `updated_at`; a
 * past-review-window doc is labelled "needs review". Web chips are a separate
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
            const tone = s.stale ? "stale" : "kb";
            const tooltip = [
              s.title,
              updated ? `Updated ${updated}` : null,
              reviewed ? `Last reviewed ${reviewed}` : null,
              s.stale ? "Past its review window" : null,
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <ChipShell key={s.payload_id || s.slug || s.title} href={s.url} tone={tone} title={tooltip}>
                {s.stale ? <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden /> : null}
                <span className="truncate">{s.title}</span>
                {updated ? <span className="shrink-0 opacity-70">· {updated}</span> : null}
                {s.stale ? <span className="shrink-0 font-medium">· needs review</span> : null}
              </ChipShell>
            );
          })}
        </div>
      )}
      {web.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 inline-flex items-center gap-1 text-xs font-medium text-gray-500">
            <Globe className="h-3.5 w-3.5" aria-hidden />
            From the web · unverified
          </span>
          {web.map((w) => (
            <ChipShell key={w.url} href={w.url} tone="web" title={`${w.title} — not reviewed by the Litecoin Foundation`}>
              <span className="truncate">{w.title}</span>
            </ChipShell>
          ))}
        </div>
      )}
    </div>
  );
}
