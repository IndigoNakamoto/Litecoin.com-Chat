"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Copy, Check } from "lucide-react";
import { LiveExternalLink, LiveStat, liveInnerCardClass } from "./LiveCardFrame";

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
    <Card className={liveInnerCardClass}>
      <CardHeader className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            Transaction
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                status.confirmed ? "bg-emerald-400/10 text-emerald-200" : "bg-amber-400/10 text-amber-200"
              }`}
            >
              {status.confirmed ? "Confirmed" : "Unconfirmed"}
            </span>
          </CardTitle>
          <LiveExternalLink href={deep_link}>View on Litecoin Space</LiveExternalLink>
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
      <CardContent className="grid grid-cols-2 gap-3 px-4 pb-4">
        <LiveStat label="Output" value={formatLitoshis(totalOutput)} />
        <LiveStat label="Fee" value={formatLitoshis(fee)} />
        <LiveStat label="Size" value={`${size.toLocaleString()} B`} />
        <LiveStat label="Inputs → outputs" value={`${vin.length} → ${vout.length}`} />
        {status.confirmed && status.block_height ? (
          <div className="col-span-2">
            <LiveStat
              label="Block"
              value={status.block_height.toLocaleString()}
              hint={status.block_time ? formatTimestamp(status.block_time) : undefined}
            />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
