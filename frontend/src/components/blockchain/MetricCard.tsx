"use client";

import React from "react";
import { ExternalLink, TrendingDown, TrendingUp, Minus, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Sparkline, { type SparkPoint } from "./Sparkline";

export type MetricUnit = "usd" | "ltc" | "percent" | "ratio" | "count" | "raw";

export interface MetricCardProps {
  metric_id: string;
  label: string;
  unit: MetricUnit | string;
  series: string;
  index: string;
  description?: string;
  status: "ok" | "not_computed";
  value: number | null;
  value_formatted?: string | null;
  /** Unix seconds of the value's bucket. */
  as_of?: number | null;
  points?: SparkPoint[];
  /** window (as string key, e.g. "7") -> % change, or null when not available */
  changes?: Record<string, number | null>;
  chart_url?: string;
  // not_computed context
  computed_height?: number | null;
  computed_at?: string | null;
  tip_height?: number | null;
}

function formatValue(value: number, unit: string): string {
  const abs = Math.abs(value);
  switch (unit) {
    case "usd":
      if (abs >= 1e9) return `$${(value / 1e9).toLocaleString(undefined, { maximumFractionDigits: 2 })}B`;
      if (abs >= 1e6) return `$${(value / 1e6).toLocaleString(undefined, { maximumFractionDigits: 2 })}M`;
      return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    case "ltc":
      if (abs >= 1e6) return `${(value / 1e6).toLocaleString(undefined, { maximumFractionDigits: 2 })}M LTC`;
      return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} LTC`;
    case "percent":
      return `${value.toFixed(2)}%`;
    case "ratio":
      return value.toFixed(3);
    case "count":
      if (abs >= 1e6) return `${(value / 1e6).toLocaleString(undefined, { maximumFractionDigits: 2 })}M`;
      return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
    default:
      if (abs >= 1e12) return value.toExponential(3);
      if (abs >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
      return value.toLocaleString(undefined, { maximumSignificantDigits: 4 });
  }
}

function formatAsOf(unix?: number | null): string | null {
  if (!unix) return null;
  const d = new Date(unix * 1000);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
}

function ChangeChip({ window, pct, indexWord }: { window: string; pct: number | null; indexWord: string }) {
  const Icon = pct === null ? Minus : pct > 0 ? TrendingUp : pct < 0 ? TrendingDown : Minus;
  const tone =
    pct === null
      ? "border-gray-200 text-gray-500 bg-gray-50"
      : pct > 0
      ? "border-emerald-200 text-emerald-700 bg-emerald-50"
      : pct < 0
      ? "border-red-200 text-red-700 bg-red-50"
      : "border-gray-200 text-gray-600 bg-gray-50";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${tone}`} data-testid={`metric-change-${window}`}>
      <Icon className="h-3 w-3" aria-hidden />
      {window}
      {indexWord}: {pct === null ? "n/a" : `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`}
    </span>
  );
}

/**
 * Live on-chain metric from litview.space: headline value, as-of date,
 * % change chips, sparkline, and a link to the source. When litview has not
 * computed the series up to now, the card says so instead of showing a number.
 */
export default function MetricCard(props: MetricCardProps) {
  const {
    label, unit, description, status, value, value_formatted, as_of, points = [], changes = {},
    chart_url, computed_height, computed_at, tip_height, index,
  } = props;
  const indexWord = index === "day1" ? "d" : index;
  const asOf = formatAsOf(as_of);
  const link = chart_url || "https://litview.space";

  return (
    <Card className="my-3 border-sky-200/60 bg-sky-50/30 dark:bg-sky-950/20 dark:border-sky-800/30" data-testid="metric-card">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center justify-between gap-2">
          <span>{label}</span>
          <span className="text-xs font-normal text-muted-foreground inline-flex items-center gap-1">
            {asOf ? (
              <>
                <Clock className="h-3 w-3" aria-hidden />
                as of {asOf} UTC
              </>
            ) : null}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {status === "ok" && value !== null && value !== undefined ? (
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="text-2xl font-semibold tracking-tight" data-testid="metric-value">
                {value_formatted || formatValue(value, unit)}
              </div>
              {Object.keys(changes).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(changes)
                    .sort((a, b) => Number(a[0]) - Number(b[0]))
                    .map(([w, pct]) => (
                      <ChangeChip key={w} window={w} pct={pct} indexWord={indexWord} />
                    ))}
                </div>
              )}
            </div>
            {points.length >= 2 && (
              <div className="text-sky-600 dark:text-sky-400 shrink-0">
                <Sparkline points={points} width={160} height={44} ariaLabel={`${label} trend`} />
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="metric-not-computed">
            <div className="font-medium">Not computed yet on litview.space</div>
            <div className="mt-1">
              {tip_height ? <>Chain indexed to block {tip_height.toLocaleString()}; </> : null}
              this series is computed through
              {computed_height ? <> block {computed_height.toLocaleString()}</> : <> an earlier height</>}
              {computed_at ? <> ({computed_at})</> : null}. No current value to show.
            </div>
          </div>
        )}

        {description ? <p className="text-xs text-muted-foreground leading-relaxed">{description}</p> : null}

        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-medium text-sky-700 hover:text-sky-900 underline underline-offset-2"
        >
          View on litview.space
          <ExternalLink className="h-3 w-3" aria-hidden />
        </a>
      </CardContent>
    </Card>
  );
}
