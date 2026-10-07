"use client";

import React from "react";
import { ExternalLink } from "lucide-react";
import ProvenanceFooter, { type LiveDataProvenance } from "./ProvenanceFooter";

/** Inner shadcn Card, with the frame owning the border, radius, and shadow. */
export const liveInnerCardClass =
  "my-0 gap-0 rounded-none border-0 bg-transparent py-0 text-foreground shadow-none";

export function LiveStat({
  label,
  value,
  hint,
  hero = false,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  hero?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{label}</div>
      <div
        className={
          hero
            ? "mt-1 font-space-grotesk text-[1.75rem] font-semibold leading-none tracking-tight text-foreground"
            : "mt-0.5 text-sm font-semibold tabular-nums text-foreground"
        }
      >
        {value}
      </div>
      {hint ? <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function LiveExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-xs font-medium text-[#0066CC] hover:text-[#004f9e]"
    >
      {children}
      <ExternalLink className="h-3 w-3" aria-hidden />
    </a>
  );
}

/**
 * Shared chrome for every live-data card: white surface, Litecoin-blue rail,
 * and the provenance line inside the card instead of floating under it.
 */
export default function LiveCardFrame({
  children,
  provenance,
  testId,
}: {
  children: React.ReactNode;
  provenance?: LiveDataProvenance;
  testId?: string;
}) {
  return (
    <section
      data-testid={testId}
      className="relative my-3 overflow-hidden rounded-2xl border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,0.35)]"
    >
      <div className="absolute inset-y-0 left-0 w-[3px] bg-[#0066CC]" aria-hidden />
      {children}
      <ProvenanceFooter provenance={provenance} />
    </section>
  );
}
