"use client";

import React, { useMemo } from "react";

export interface SparkPoint {
  t?: number | null;
  v: number | null;
}

interface SparklineProps {
  points: SparkPoint[];
  width?: number;
  height?: number;
  /** Stroke colour; defaults to currentColor so the parent sets it. */
  stroke?: string;
  className?: string;
  ariaLabel?: string;
}

/**
 * Dependency-free SVG sparkline. Null gaps break the line rather than being
 * interpolated, so a half-computed series is drawn honestly.
 */
export default function Sparkline({
  points,
  width = 160,
  height = 40,
  stroke = "currentColor",
  className,
  ariaLabel = "trend",
}: SparklineProps) {
  const { segments, lastDot, min, max } = useMemo(() => {
    const vals = points.map((p) => (typeof p.v === "number" && Number.isFinite(p.v) ? p.v : null));
    const finite = vals.filter((v): v is number => v !== null);
    if (finite.length < 2) return { segments: [] as string[], lastDot: null as { x: number; y: number } | null, min: 0, max: 0 };
    const lo = Math.min(...finite);
    const hi = Math.max(...finite);
    const pad = 3;
    const span = hi - lo || 1;
    const n = vals.length;
    const x = (i: number) => (n === 1 ? width / 2 : pad + (i * (width - 2 * pad)) / (n - 1));
    const y = (v: number) => height - pad - ((v - lo) / span) * (height - 2 * pad);

    const segs: string[] = [];
    let current: string[] = [];
    let last: { x: number; y: number } | null = null;
    vals.forEach((v, i) => {
      if (v === null) {
        if (current.length > 1) segs.push(current.join(" "));
        current = [];
        return;
      }
      const px = x(i);
      const py = y(v);
      current.push(`${px.toFixed(1)},${py.toFixed(1)}`);
      last = { x: px, y: py };
    });
    if (current.length > 1) segs.push(current.join(" "));
    return { segments: segs, lastDot: last, min: lo, max: hi };
  }, [points, width, height]);

  if (segments.length === 0) return null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${ariaLabel}: from ${min} to ${max}`}
      className={className}
      data-testid="sparkline"
    >
      {segments.map((pts, i) => (
        <polyline
          key={i}
          points={pts}
          fill="none"
          stroke={stroke}
          strokeWidth={1.75}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {lastDot && <circle cx={lastDot.x} cy={lastDot.y} r={2.5} fill={stroke} />}
    </svg>
  );
}
