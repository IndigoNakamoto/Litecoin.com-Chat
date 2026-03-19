"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExternalLink, Copy, Check } from "lucide-react";

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
    <Card className="my-3 border-emerald-200/50 bg-emerald-50/30 dark:bg-emerald-950/20 dark:border-emerald-800/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm font-medium">
            Block {height.toLocaleString()}
          </CardTitle>
          <a
            href={deep_link}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 flex items-center gap-1"
          >
            View on Litecoin Space
            <ExternalLink className="w-3 h-3" />
          </a>
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
      <CardContent className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        <div className="col-span-2">
          <span className="text-muted-foreground">Time:</span>{" "}
          <span className="font-medium">{formatTimestamp(timestamp)}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Transactions:</span>{" "}
          <span className="font-medium">{tx_count.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Size:</span>{" "}
          <span className="font-medium">{formatSize(size)}</span>
        </div>
        <div className="col-span-2">
          <span className="text-muted-foreground">Difficulty:</span>{" "}
          <span className="font-medium">{difficulty.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        </div>
      </CardContent>
    </Card>
  );
}
