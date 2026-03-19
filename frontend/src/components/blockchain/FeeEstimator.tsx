"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface FeeEstimatorProps {
  fastestFee: number;
  halfHourFee: number;
  hourFee: number;
  economyFee: number;
  minimumFee: number;
}

const tiers = [
  { key: "fastestFee", label: "Next Block", icon: "⚡", description: "~2.5 min" },
  { key: "halfHourFee", label: "30 Minutes", icon: "🕐", description: "~12 blocks" },
  { key: "hourFee", label: "1 Hour", icon: "🕑", description: "~24 blocks" },
  { key: "economyFee", label: "Economy", icon: "💰", description: "Low priority" },
] as const;

export default function FeeEstimator(props: FeeEstimatorProps) {
  const maxFee = Math.max(props.fastestFee, 1);

  return (
    <Card className="my-3 border-amber-200/50 bg-amber-50/30 dark:bg-amber-950/20 dark:border-amber-800/30">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Recommended Fees
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {tiers.map((tier) => {
          const fee = props[tier.key];
          const width = Math.max((fee / maxFee) * 100, 8);
          return (
            <div key={tier.key} className="flex items-center gap-3">
              <span className="text-base w-6 text-center">{tier.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between text-sm mb-0.5">
                  <span className="font-medium">{tier.label}</span>
                  <span className="font-mono text-muted-foreground">
                    {fee} lit/vB
                  </span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                  <div
                    className="bg-amber-500 dark:bg-amber-400 h-1.5 rounded-full transition-all"
                    style={{ width: `${width}%` }}
                  />
                </div>
                <span className="text-xs text-muted-foreground">
                  {tier.description}
                </span>
              </div>
            </div>
          );
        })}
        <div className="text-xs text-muted-foreground pt-1 border-t border-gray-200 dark:border-gray-700">
          Minimum relay fee: {props.minimumFee} lit/vB
        </div>
      </CardContent>
    </Card>
  );
}
