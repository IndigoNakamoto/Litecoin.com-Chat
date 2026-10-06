"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Copy, Check } from "lucide-react";
import { LiveExternalLink, LiveStat, liveInnerCardClass } from "./LiveCardFrame";

interface AddressStats {
  funded_txo_count: number;
  funded_txo_sum: number;
  spent_txo_count: number;
  spent_txo_sum: number;
  tx_count: number;
}

interface AddressCardProps {
  address: string;
  chain_stats: AddressStats;
  mempool_stats: AddressStats;
  deep_link: string;
}

function truncateAddress(addr: string): string {
  if (addr.length <= 20) return addr;
  return `${addr.slice(0, 12)}...${addr.slice(-8)}`;
}

function formatLTC(litoshis: number): string {
  return `${(litoshis / 1e8).toFixed(8)} LTC`;
}

export default function AddressCard({
  address,
  chain_stats,
  mempool_stats,
  deep_link,
}: AddressCardProps) {
  const [copied, setCopied] = React.useState(false);

  const balance =
    chain_stats.funded_txo_sum +
    mempool_stats.funded_txo_sum -
    chain_stats.spent_txo_sum -
    mempool_stats.spent_txo_sum;

  const totalTx = chain_stats.tx_count + mempool_stats.tx_count;

  const copyAddress = () => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card className={liveInnerCardClass}>
      <CardHeader className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm font-medium">Address</CardTitle>
          <LiveExternalLink href={deep_link}>View on Litecoin Space</LiveExternalLink>
        </div>
        <button
          onClick={copyAddress}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground font-mono mt-1 transition-colors"
        >
          {truncateAddress(address)}
          {copied ? (
            <Check className="w-3 h-3 text-green-500" />
          ) : (
            <Copy className="w-3 h-3" />
          )}
        </button>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 px-4 pb-4">
        <div className="col-span-2">
          <LiveStat label="Balance" hero value={formatLTC(balance)} />
        </div>
        <LiveStat label="Received" value={formatLTC(chain_stats.funded_txo_sum)} />
        <LiveStat label="Sent" value={formatLTC(chain_stats.spent_txo_sum)} />
        <LiveStat label="Transactions" value={totalTx.toLocaleString()} />
        {mempool_stats.tx_count > 0 ? (
          <LiveStat label="Pending" value={mempool_stats.tx_count} />
        ) : null}
      </CardContent>
    </Card>
  );
}
