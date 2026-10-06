"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LiveExternalLink, LiveStat, liveInnerCardClass } from "./LiveCardFrame";

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
    <Card className={liveInnerCardClass}>
      <CardHeader className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="font-space-grotesk text-lg font-semibold">{pool.name || pool.slug || "Mining pool"}</CardTitle>
          {pool.link ? <LiveExternalLink href={pool.link}>Pool website</LiveExternalLink> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 px-4 pb-4 text-sm">
        <div className="grid grid-cols-2 gap-3">
          {typeof estimatedHashrate === "number" ? (
            <LiveStat label="Estimated hashrate" value={formatHashrate(estimatedHashrate)} />
          ) : null}
          {reported ? <LiveStat label="Reported" value={reported} /> : null}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {WINDOWS.map((w) => (
            <div key={w} className="rounded-lg border border-[#e3e8ef] bg-[#f7f9fb] p-2">
              <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#6b7280]">{w}</div>
              <div className="mt-0.5 text-sm font-semibold tabular-nums">{(blockCount?.[w] ?? 0).toLocaleString()}</div>
              <div className="text-[11px] text-[#6b7280]">{pct(blockShare?.[w])} share</div>
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
