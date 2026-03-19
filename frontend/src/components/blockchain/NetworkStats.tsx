"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface NetworkStatsProps {
  hashrate?: { current_hashrate: number; current_difficulty: number };
  difficulty_adjustment?: {
    progressPercent: number;
    difficultyChange: number;
    remainingBlocks: number;
    estimatedRetargetDate: number;
  };
  price?: {
    USD: number;
    EUR: number;
    GBP: number;
    AUD: number;
    JPY: number;
    time: number;
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

export default function NetworkStats({
  hashrate,
  difficulty_adjustment,
  price,
}: NetworkStatsProps) {
  return (
    <Card className="my-3 border-indigo-200/50 bg-indigo-50/30 dark:bg-indigo-950/20 dark:border-indigo-800/30">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center justify-between">
          <span>{price ? "Litecoin Price" : "Network Stats"}</span>
          {price?.time ? (
            <span className="text-xs font-normal text-muted-foreground">
              {timeAgo(price.time)}
            </span>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {price && (
          <div className="grid grid-cols-3 gap-x-4 gap-y-1.5">
            <div>
              <span className="text-muted-foreground">USD</span>
              <div className="font-semibold">${price.USD.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div>
              <span className="text-muted-foreground">EUR</span>
              <div className="font-semibold">€{price.EUR.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div>
              <span className="text-muted-foreground">GBP</span>
              <div className="font-semibold">£{price.GBP.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div>
              <span className="text-muted-foreground">AUD</span>
              <div className="font-medium">A${price.AUD.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div>
              <span className="text-muted-foreground">JPY</span>
              <div className="font-medium">¥{price.JPY.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
            </div>
          </div>
        )}

        {hashrate && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            <div>
              <span className="text-muted-foreground">Hashrate:</span>{" "}
              <span className="font-medium">
                {formatHashrate(hashrate.current_hashrate)}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">Difficulty:</span>{" "}
              <span className="font-medium">
                {hashrate.current_difficulty.toLocaleString(undefined, {
                  maximumFractionDigits: 2,
                })}
              </span>
            </div>
          </div>
        )}

        {difficulty_adjustment && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Next adjustment ({difficulty_adjustment.remainingBlocks.toLocaleString()} blocks)
              </span>
              <span className="font-medium">
                {difficulty_adjustment.difficultyChange >= 0 ? "+" : ""}
                {difficulty_adjustment.difficultyChange.toFixed(2)}%
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
              <div
                className="bg-indigo-500 dark:bg-indigo-400 h-1.5 rounded-full transition-all"
                style={{
                  width: `${Math.min(difficulty_adjustment.progressPercent, 100)}%`,
                }}
              />
            </div>
            <div className="text-xs text-muted-foreground text-right">
              {difficulty_adjustment.progressPercent.toFixed(1)}% complete
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
