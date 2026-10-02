"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExternalLink } from "lucide-react";

interface PoolInfo {
  name?: string;
  slug?: string;
  link?: string;
  addresses?: string[];
}

interface MiningPoolCardProps {
  pool: PoolInfo;
  blockCount?: Record<string, number | undefined>;
  blockShare?: Record<string, number | undefined>;
  estimatedHashrate?: number;
  reportedHashrate?: number | string | null;
}

function formatHashrate(hs: number): string {
  if (hs >= 1e18) return `${(hs / 1e18).toFixed(2)} EH/s`;
  if (hs >= 1e15) return `${(hs / 1e15).toFixed(2)} PH/s`;
  if (hs >= 1e12) return `${(hs / 1e12).toFixed(2)} TH/s`;
  if (hs >= 1e9) return `${(hs / 1e9).toFixed(2)} GH/s`;
  return `${hs.toFixed(0)} H/s`;
}

function pct(v?: number): string {
  if (typeof v !== "number") return "n/a";
  return `${(v * 100).toFixed(2)}%`;
}

const WINDOWS = ["24h", "1w", "all"] as const;

export default function MiningPoolCard({
  pool,
  blockCount,
  blockShare,
  estimatedHashrate,
  reportedHashrate,
}: MiningPoolCardProps) {
  const reported = typeof reportedHashrate === "number" ? formatHashrate(reportedHashrate) : reportedHashrate;
  return (
    <Card className="my-3 border-orange-200/50 bg-orange-50/30 dark:bg-orange-950/20 dark:border-orange-800/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm font-medium">{pool.name || pool.slug || "Mining pool"}</CardTitle>
          {pool.link ? (
            <a
              href={pool.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 flex items-center gap-1"
            >
              Pool website
              <ExternalLink className="w-3 h-3" />
            </a>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          {typeof estimatedHashrate === "number" ? (
            <div>
              <span className="text-muted-foreground">Est. hashrate:</span>{" "}
              <span className="font-medium">{formatHashrate(estimatedHashrate)}</span>
            </div>
          ) : null}
          {reported ? (
            <div>
              <span className="text-muted-foreground">Reported:</span>{" "}
              <span className="font-medium">{reported}</span>
            </div>
          ) : null}
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs">
          {WINDOWS.map((w) => (
            <div key={w} className="rounded-md border border-orange-200/60 dark:border-orange-800/40 p-2">
              <div className="text-muted-foreground uppercase">{w}</div>
              <div className="font-semibold">{(blockCount?.[w] ?? 0).toLocaleString()} blocks</div>
              <div className="text-muted-foreground">{pct(blockShare?.[w])} share</div>
            </div>
          ))}
        </div>
        {pool.addresses && pool.addresses.length > 0 ? (
          <div className="text-xs text-muted-foreground font-mono truncate">
            Coinbase: {pool.addresses.slice(0, 2).join(", ")}
            {pool.addresses.length > 2 ? ` +${pool.addresses.length - 2} more` : ""}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
