"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Copy, Check } from "lucide-react";
import { LiveExternalLink, LiveStat, liveInnerCardClass } from "./LiveCardFrame";

interface BlockCardProps {
  id: string;
  height: number;
  timestamp: number;
  tx_count: number;
  size: number;
  weight: number;
  difficulty: number;
  deep_link: string;
}

function truncateHash(hash: string): string {
  if (hash.length <= 24) return hash;
  return `${hash.slice(0, 14)}...${hash.slice(-8)}`;
}

function formatTimestamp(unixTs: number): string {
  return new Date(unixTs * 1000).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function formatSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(2)} MB`;
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`;
  return `${bytes} B`;
}

export default function BlockCard({
  id,
  height,
  timestamp,
  tx_count,
  size,
  weight: _weight,
  difficulty,
  deep_link,
}: BlockCardProps) {
  const [copied, setCopied] = React.useState(false);

  const copyHash = () => {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card className={liveInnerCardClass}>
      <CardHeader className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="font-space-grotesk text-lg font-semibold">
            Block {height.toLocaleString()}
          </CardTitle>
          <LiveExternalLink href={deep_link}>View on Litecoin Space</LiveExternalLink>
        </div>
        <button
          onClick={copyHash}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground font-mono mt-1 transition-colors"
        >
          {truncateHash(id)}
          {copied ? (
            <Check className="w-3 h-3 text-green-500" />
          ) : (
            <Copy className="w-3 h-3" />
          )}
        </button>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 px-4 pb-4">
        <div className="col-span-2">
          <LiveStat label="Time" value={formatTimestamp(timestamp)} />
        </div>
        <LiveStat label="Transactions" value={tx_count.toLocaleString()} />
        <LiveStat label="Size" value={formatSize(size)} />
        <div className="col-span-2">
          <LiveStat label="Difficulty" value={difficulty.toLocaleString(undefined, { maximumFractionDigits: 2 })} />
        </div>
      </CardContent>
    </Card>
  );
}
