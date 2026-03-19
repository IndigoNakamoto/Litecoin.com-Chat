"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface MempoolStatusProps {
  count: number;
  vsize: number;
  total_fee: number;
}

function getCongestionLevel(vsizeMB: number): {
  label: string;
  color: string;
} {
  if (vsizeMB < 1) return { label: "Low", color: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300" };
  if (vsizeMB < 5) return { label: "Moderate", color: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300" };
  return { label: "High", color: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300" };
}

export default function MempoolStatus({ count, vsize, total_fee }: MempoolStatusProps) {
  const vsizeMB = vsize / 1_000_000;
  const congestion = getCongestionLevel(vsizeMB);

  return (
    <Card className="my-3 border-cyan-200/50 bg-cyan-50/30 dark:bg-cyan-950/20 dark:border-cyan-800/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Mempool Status</CardTitle>
          <Badge variant="secondary" className={congestion.color}>
            {congestion.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        <div>
          <span className="text-muted-foreground">Unconfirmed:</span>{" "}
          <span className="font-medium">{count.toLocaleString()} txs</span>
        </div>
        <div>
          <span className="text-muted-foreground">Size:</span>{" "}
          <span className="font-medium">{vsizeMB.toFixed(2)} MB</span>
        </div>
        <div className="col-span-2">
          <span className="text-muted-foreground">Total Fees:</span>{" "}
          <span className="font-medium">
            {(total_fee / 1e8).toFixed(8)} LTC
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
