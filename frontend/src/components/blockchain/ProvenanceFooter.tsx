"use client";

import React from "react";
import { Clock, Database } from "lucide-react";

export interface LiveDataProvenance {
  source?: string;
  endpoint?: string;
  fetched_at?: string;
}

function formatFetchedAt(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  });
}

/**
 * Timestamp + endpoint line under every live-data card.
 *
 * Live numbers are rendered by cards, not prose the model can round, and
 * each card says exactly when and from where the number was fetched.
 */
export default function ProvenanceFooter({ provenance }: { provenance?: LiveDataProvenance }) {
  if (!provenance) return null;
  const fetched = formatFetchedAt(provenance.fetched_at);
  const source = provenance.source || "Litecoin Space";
  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[#eef2f6] bg-[#f7f9fb] px-4 py-2 text-[11px] text-[#6b7280]"
      data-testid="live-data-provenance"
    >
      {fetched ? (
        <span className="inline-flex items-center gap-1">
          <Clock className="h-3 w-3" aria-hidden />
          Fetched {fetched}
        </span>
      ) : null}
      {provenance.endpoint ? (
        <span className="inline-flex items-center gap-1 font-mono">
          <Database className="h-3 w-3" aria-hidden />
          {source} {provenance.endpoint}
        </span>
      ) : null}
    </div>
  );
}
