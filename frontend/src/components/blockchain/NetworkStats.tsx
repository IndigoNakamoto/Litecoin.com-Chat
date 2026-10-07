"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LiveStat, liveInnerCardClass } from "./LiveCardFrame";

interface NetworkStatsProps {
  hashrate?: { current_hashrate: number; current_difficulty: number; basis?: string };
  difficulty_adjustment?: {
    progressPercent: number;
    difficultyChange: number;
    remainingBlocks: number;
    estimatedRetargetDate: number;
  };
  price?: {
    USD?: number;
    EUR?: number;
    GBP?: number;
    AUD?: number;
    JPY?: number;
    time?: number;
  };
}

function timeAgo(unixSeconds: number): string {
  const delta = Math.floor(Date.now() / 1000) - unixSeconds;
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

function formatHashrate(hs: number): string {
  if (hs >= 1e18) return `${(hs / 1e18).toFixed(2)} EH/s`;
  if (hs >= 1e15) return `${(hs / 1e15).toFixed(2)} PH/s`;
  if (hs >= 1e12) return `${(hs / 1e12).toFixed(2)} TH/s`;
  if (hs >= 1e9) return `${(hs / 1e9).toFixed(2)} GH/s`;
  return `${hs.toFixed(0)} H/s`;
}

function money(value: number, digits: number): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

const OTHER_FIAT = [
  { code: "EUR", prefix: "€", digits: 2 },
  { code: "GBP", prefix: "£", digits: 2 },
  { code: "AUD", prefix: "A$", digits: 2 },
  { code: "JPY", prefix: "¥", digits: 0 },
] as const;

export default function NetworkStats({
  hashrate,
  difficulty_adjustment,
  price,
}: NetworkStatsProps) {
  const others = price
    ? OTHER_FIAT.flatMap((row) => {
        const value = price[row.code];
        return typeof value === "number" && value > 0 ? [{ ...row, value }] : [];
      })
    : [];
  const hashrateHint = hashrate?.basis === "daily" ? "Daily average" : hashrate?.basis === "3d" ? "3-day estimate" : undefined;

  return (
    <Card className={liveInnerCardClass}>
      <CardHeader className="px-4 pt-4 pb-2">
        <CardTitle className="text-sm font-medium flex items-center justify-between gap-2">
          <span>{price ? "Litecoin price" : "Network"}</span>
          {price?.time ? (
            <span className="text-xs font-normal text-muted-foreground">{timeAgo(price.time)}</span>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 px-4 pb-4 text-sm">
        {price && typeof price.USD === "number" && price.USD > 0 ? (
          <div className="space-y-3">
            <LiveStat label="USD" hero value={`$${money(price.USD, 2)}`} />
            {others.length > 0 ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {others.map((row) => (
                  <LiveStat
                    key={row.code}
                    label={row.code}
                    value={`${row.prefix}${money(row.value, row.digits)}`}
                  />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {hashrate ? (
          <div className="grid grid-cols-2 gap-4">
            <LiveStat label="Hashrate" hero value={formatHashrate(hashrate.current_hashrate)} hint={hashrateHint} />
            <LiveStat
              label="Difficulty"
              hero
              value={hashrate.current_difficulty.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            />
          </div>
        ) : null}

        {difficulty_adjustment ? (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Next adjustment · {difficulty_adjustment.remainingBlocks.toLocaleString()} blocks
              </span>
              <span className="font-semibold tabular-nums text-foreground">
                {difficulty_adjustment.difficultyChange >= 0 ? "+" : ""}
                {difficulty_adjustment.difficultyChange.toFixed(2)}%
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-white/10">
              <div
                className="h-1.5 rounded-full bg-[#0066CC] transition-all"
                style={{ width: `${Math.min(difficulty_adjustment.progressPercent, 100)}%` }}
              />
            </div>
            <div className="text-right text-[11px] text-muted-foreground">
              {difficulty_adjustment.progressPercent.toFixed(1)}% of this epoch
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
