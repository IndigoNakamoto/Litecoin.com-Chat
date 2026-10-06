"use client";

import React from "react";
import TransactionCard from "./TransactionCard";
import AddressCard from "./AddressCard";
import BlockCard from "./BlockCard";
import FeeEstimator, { type FeeCostContext } from "./FeeEstimator";
import MempoolStatus from "./MempoolStatus";
import NetworkStats from "./NetworkStats";
import MiningPoolsCard, { type MiningPoolRow } from "./MiningPoolsCard";
import MiningPoolCard from "./MiningPoolCard";
import MetricCard, { type MetricCardProps } from "./MetricCard";
import LiveCardFrame from "./LiveCardFrame";
import { type LiveDataProvenance } from "./ProvenanceFooter";

interface BlockchainDataRendererProps {
  dataType: string;
  data: Record<string, unknown>;
}

function renderCard(dataType: string, data: Record<string, unknown>): React.ReactElement | null {
  switch (dataType) {
    case "transaction":
      return (
        <TransactionCard
          txid={data.txid as string}
          fee={data.fee as number}
          size={data.size as number}
          weight={data.weight as number}
          status={data.status as { confirmed: boolean; block_height?: number; block_hash?: string; block_time?: number }}
          vin={data.vin as Array<Record<string, unknown>>}
          vout={data.vout as Array<Record<string, unknown>>}
          deep_link={data.deep_link as string}
        />
      );

    case "address":
      return (
        <AddressCard
          address={data.address as string}
          chain_stats={data.chain_stats as { funded_txo_count: number; funded_txo_sum: number; spent_txo_count: number; spent_txo_sum: number; tx_count: number }}
          mempool_stats={data.mempool_stats as { funded_txo_count: number; funded_txo_sum: number; spent_txo_count: number; spent_txo_sum: number; tx_count: number }}
          deep_link={data.deep_link as string}
        />
      );

    case "block":
    case "block_tip":
      return (
        <BlockCard
          id={data.id as string}
          height={data.height as number}
          timestamp={data.timestamp as number}
          tx_count={data.tx_count as number}
          size={data.size as number}
          weight={data.weight as number}
          difficulty={data.difficulty as number}
          deep_link={data.deep_link as string}
        />
      );

    case "fees":
      return (
        <FeeEstimator
          fastestFee={data.fastestFee as number}
          halfHourFee={data.halfHourFee as number}
          hourFee={data.hourFee as number}
          economyFee={data.economyFee as number}
          minimumFee={data.minimumFee as number}
          context={data.context as FeeCostContext | undefined}
        />
      );

    case "mempool":
      return (
        <MempoolStatus
          count={data.count as number}
          vsize={data.vsize as number}
          total_fee={data.total_fee as number}
        />
      );

    case "hashrate":
      return (
        <NetworkStats
          hashrate={data.hashrate as { current_hashrate: number; current_difficulty: number } | undefined}
          difficulty_adjustment={data.difficulty_adjustment as { progressPercent: number; difficultyChange: number; remainingBlocks: number; estimatedRetargetDate: number } | undefined}
        />
      );

    case "price":
      return (
        <NetworkStats
          price={data as unknown as { USD: number; EUR: number; GBP: number; AUD: number; JPY: number; time: number }}
        />
      );

    case "mining_pools":
      return (
        <MiningPoolsCard
          pools={(data.pools as MiningPoolRow[]) || []}
          blockCount={data.blockCount as number | undefined}
          lastEstimatedHashrate={data.lastEstimatedHashrate as number | undefined}
          period={data.period as string | undefined}
        />
      );

    case "mining_pool":
      return (
        <MiningPoolCard
          pool={(data.pool as { name?: string; slug?: string; link?: string; addresses?: string[] }) || {}}
          blockCount={data.blockCount as Record<string, number | undefined> | undefined}
          blockShare={data.blockShare as Record<string, number | undefined> | undefined}
          estimatedHashrate={data.estimatedHashrate as number | undefined}
          reportedHashrate={data.reportedHashrate as number | string | null | undefined}
        />
      );

    case "metric":
      // On-chain metric from litview.space (see backend/data/metrics_registry.yaml).
      return <MetricCard {...(data as unknown as MetricCardProps)} />;

    default:
      return null;
  }
}

/**
 * Dispatches a `blockchain_data` SSE event to the matching card and appends
 * the shared provenance footer (fetched_at + endpoint) under every card.
 */
export default function BlockchainDataRenderer({
  dataType,
  data,
}: BlockchainDataRendererProps) {
  const card = renderCard(dataType, data);
  if (!card) return null;
  const provenance = data._provenance as LiveDataProvenance | undefined;
  return (
    <LiveCardFrame provenance={provenance} testId={`blockchain-card-${dataType}`}>
      {card}
    </LiveCardFrame>
  );
}
