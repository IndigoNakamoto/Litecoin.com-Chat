"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExternalLink, Copy, Check } from "lucide-react";

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
    <Card className="my-3 border-purple-200/50 bg-purple-50/30 dark:bg-purple-950/20 dark:border-purple-800/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm font-medium">Address</CardTitle>
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
      <CardContent className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        <div className="col-span-2">
          <span className="text-muted-foreground">Balance:</span>{" "}
          <span className="font-semibold">{formatLTC(balance)}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Received:</span>{" "}
          <span className="font-medium">{formatLTC(chain_stats.funded_txo_sum)}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Sent:</span>{" "}
          <span className="font-medium">{formatLTC(chain_stats.spent_txo_sum)}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Transactions:</span>{" "}
          <span className="font-medium">{totalTx.toLocaleString()}</span>
        </div>
        {mempool_stats.tx_count > 0 && (
          <div>
            <span className="text-muted-foreground">Pending:</span>{" "}
            <span className="font-medium text-yellow-600">
              {mempool_stats.tx_count}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
