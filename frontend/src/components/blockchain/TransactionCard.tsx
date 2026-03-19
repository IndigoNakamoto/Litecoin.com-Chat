"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, Copy, Check } from "lucide-react";

interface TransactionStatus {
  confirmed: boolean;
  block_height?: number;
  block_hash?: string;
  block_time?: number;
}

interface TransactionCardProps {
  txid: string;
  fee: number;
  size: number;
  weight: number;
  status: TransactionStatus;
  vin: Array<Record<string, unknown>>;
  vout: Array<Record<string, unknown>>;
  deep_link: string;
}

function truncateHash(hash: string, start = 10, end = 6): string {
  if (hash.length <= start + end + 3) return hash;
  return `${hash.slice(0, start)}...${hash.slice(-end)}`;
}

function formatLitoshis(litoshis: number): string {
  return `${(litoshis / 1e8).toFixed(8)} LTC`;
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

export default function TransactionCard({
  txid,
  fee,
  size,
  weight: _weight,
  status,
  vin,
  vout,
  deep_link,
}: TransactionCardProps) {
  const [copied, setCopied] = React.useState(false);
  const totalOutput = vout.reduce(
    (sum, v) => sum + ((v.value as number) || 0),
    0
  );

  const copyTxid = () => {
    navigator.clipboard.writeText(txid);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card className="my-3 border-blue-200/50 bg-blue-50/30 dark:bg-blue-950/20 dark:border-blue-800/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            Transaction
            <Badge
              variant={status.confirmed ? "default" : "secondary"}
              className={
                status.confirmed
                  ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
                  : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300"
              }
            >
              {status.confirmed ? "Confirmed" : "Unconfirmed"}
            </Badge>
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
          onClick={copyTxid}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground font-mono mt-1 transition-colors"
        >
          {truncateHash(txid)}
          {copied ? (
            <Check className="w-3 h-3 text-green-500" />
          ) : (
            <Copy className="w-3 h-3" />
          )}
        </button>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        <div>
          <span className="text-muted-foreground">Output:</span>{" "}
          <span className="font-medium">{formatLitoshis(totalOutput)}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Fee:</span>{" "}
          <span className="font-medium">{formatLitoshis(fee)}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Size:</span>{" "}
          <span className="font-medium">
            {size.toLocaleString()} B
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">I/O:</span>{" "}
          <span className="font-medium">
            {vin.length} → {vout.length}
          </span>
        </div>
        {status.confirmed && status.block_height && (
          <div className="col-span-2">
            <span className="text-muted-foreground">Block:</span>{" "}
            <span className="font-medium">
              {status.block_height.toLocaleString()}
            </span>
            {status.block_time && (
              <span className="text-muted-foreground text-xs ml-2">
                ({formatTimestamp(status.block_time)})
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
