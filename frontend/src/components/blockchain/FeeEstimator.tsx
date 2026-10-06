"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { liveInnerCardClass } from "./LiveCardFrame";

export interface FeeCostContext {
  usdLabel: string;
  avgVbytes: number;
  blockCount: number;
  hourCostLabel: string;
  costs: Partial<Record<"fastestFee" | "halfHourFee" | "hourFee" | "economyFee" | "minimumFee", string>>;
}

interface FeeEstimatorProps {
  fastestFee: number;
  halfHourFee: number;
  hourFee: number;
  economyFee: number;
  minimumFee: number;
  context?: FeeCostContext | null;
}

const tiers = [
  { key: "fastestFee", label: "Next block", hint: "~2.5 min" },
  { key: "halfHourFee", label: "30 minutes", hint: "~12 blocks" },
  { key: "hourFee", label: "1 hour", hint: "~24 blocks" },
  { key: "economyFee", label: "Economy", hint: "Low priority" },
] as const;

export default function FeeEstimator(props: FeeEstimatorProps) {
  const maxFee = Math.max(props.fastestFee, props.halfHourFee, props.hourFee, props.economyFee, 1);
  const context = props.context ?? null;
  const windowLabel = context
    ? `last ${context.blockCount} ${context.blockCount === 1 ? "block" : "blocks"}`
    : "";

  return (
    <Card className={liveInnerCardClass}>
      <CardHeader className="px-4 pt-4 pb-2">
        <CardTitle className="text-sm font-medium">Recommended fees</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 px-4 pb-4">
        {tiers.map((tier) => {
          const fee = props[tier.key];
          const width = Math.max((fee / maxFee) * 100, fee > 0 ? 8 : 0);
          const cost = context?.costs?.[tier.key];
          return (
            <div key={tier.key}>
              <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                <span className="font-medium text-[#222222]">{tier.label}</span>
                <span className="font-space-grotesk text-base font-semibold tabular-nums text-[#222222]">
                  {fee} <span className="text-xs font-medium text-[#6b7280]">lit/vB</span>
                  {cost ? <span className="ml-1.5 text-xs font-medium text-[#6b7280]">{cost}</span> : null}
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-[#e8eef5]">
                <div className="h-1.5 rounded-full bg-[#0066CC]" style={{ width: `${width}%` }} />
              </div>
              <div className="mt-1 text-[11px] text-[#6b7280]">{tier.hint}</div>
            </div>
          );
        })}
        <div className="border-t border-[#eef2f6] pt-2 text-xs text-[#6b7280]">
          Minimum relay fee{" "}
          <span className="font-semibold tabular-nums text-[#222222]">
            {props.minimumFee} lit/vB
            {context?.costs?.minimumFee ? ` · ${context.costs.minimumFee}` : ""}
          </span>
        </div>
        {context ? (
          <p className="text-xs leading-relaxed text-[#6b7280]">
            About <span className="font-semibold text-[#222222]">{context.hourCostLabel}</span> per
            transaction at the 1-hour rate
            <span className="mx-1">·</span>
            {context.usdLabel}/LTC
            <span className="mx-1">·</span>
            {context.avgVbytes.toLocaleString()} vB average ({windowLabel})
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
