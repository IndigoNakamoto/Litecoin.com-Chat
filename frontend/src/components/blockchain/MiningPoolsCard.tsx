"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExternalLink } from "lucide-react";

export interface MiningPoolRow {
  rank?: number;
  name?: string;
  slug?: string;
  link?: string;
  blockCount?: number;
  share?: number;
}

interface MiningPoolsCardProps {
  pools: MiningPoolRow[];
  blockCount?: number;
  lastEstimatedHashrate?: number;
  period?: string;
}

function formatHashrate(hs: number): string {
  if (hs >= 1e18) return `${(hs / 1e18).toFixed(2)} EH/s`;
  if (hs >= 1e15) return `${(hs / 1e15).toFixed(2)} PH/s`;
  if (hs >= 1e12) return `${(hs / 1e12).toFixed(2)} TH/s`;
  if (hs >= 1e9) return `${(hs / 1e9).toFixed(2)} GH/s`;
  return `${hs.toFixed(0)} H/s`;
}

export default function MiningPoolsCard({
  pools,
  blockCount,
  lastEstimatedHashrate,
  period,
}: MiningPoolsCardProps) {
  const rows = (pools || []).slice(0, 10);
  const total = typeof blockCount === "number" && blockCount > 0 ? blockCount : rows.reduce((a, p) => a + (p.blockCount || 0), 0);

  return (
    <Card className="my-3 border-orange-200/50 bg-orange-50/30 dark:bg-orange-950/20 dark:border-orange-800/30">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center justify-between">
          <span>Mining Pools{period ? ` (${period.toUpperCase()})` : ""}</span>
          {typeof lastEstimatedHashrate === "number" ? (
            <span className="text-xs font-normal text-muted-foreground">
              Est. network {formatHashrate(lastEstimatedHashrate)}
            </span>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm">
        {rows.map((p, i) => {
          const blocks = p.blockCount ?? 0;
          const pct = total > 0 ? (blocks / total) * 100 : 0;
          return (
            <div key={p.slug || p.name || i} className="space-y-0.5">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate">
                  <span className="text-muted-foreground mr-1.5">{p.rank ?? i + 1}.</span>
                  <span className="font-medium">{p.name || p.slug || "Unknown"}</span>
                  {p.link ? (
                    <a
                      href={p.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-1.5 inline-flex items-center text-blue-600 hover:text-blue-800 dark:text-blue-400"
                      aria-label={`${p.name || p.slug} website`}
                    >
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  ) : null}
                </span>
                <span className="font-mono text-xs text-muted-foreground whitespace-nowrap">
                  {blocks.toLocaleString()} blocks · {pct.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1">
                <div
                  className="bg-orange-500 dark:bg-orange-400 h-1 rounded-full transition-all"
                  style={{ width: `${Math.max(Math.min(pct, 100), 1)}%` }}
                />
              </div>
            </div>
          );
        })}
        {pools && pools.length > rows.length ? (
          <div className="text-xs text-muted-foreground pt-1">
            Showing top {rows.length} of {pools.length} pools
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
