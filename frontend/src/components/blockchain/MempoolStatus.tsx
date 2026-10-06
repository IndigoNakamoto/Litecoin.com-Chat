"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LiveStat, liveInnerCardClass } from "./LiveCardFrame";

interface MempoolStatusProps {
  count: number;
  vsize: number;
  total_fee: number;
}

function congestion(vsizeMB: number): { label: string; className: string } {
  if (vsizeMB < 1) return { label: "Low", className: "bg-emerald-50 text-emerald-800" };
  if (vsizeMB < 5) return { label: "Moderate", className: "bg-amber-50 text-amber-800" };
  return { label: "High", className: "bg-red-50 text-red-800" };
}

export default function MempoolStatus({ count, vsize, total_fee }: MempoolStatusProps) {
  const vsizeMB = vsize / 1_000_000;
  const level = congestion(vsizeMB);

  return (
    <Card className={liveInnerCardClass}>
      <CardHeader className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-medium">Mempool</CardTitle>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${level.className}`}>{level.label}</span>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-3 gap-3 px-4 pb-4">
        <LiveStat label="Unconfirmed" value={count.toLocaleString()} hint="transactions" />
        <LiveStat label="Size" value={`${vsizeMB.toFixed(2)} MB`} />
        <LiveStat label="Fees" value={`${(total_fee / 1e8).toFixed(4)} LTC`} />
      </CardContent>
    </Card>
  );
}
