"""
Blockchain Lookup Node

Fetches live data from the Litecoin Space API when the intent classifier
detects a blockchain data query (transaction, address, block, fees, etc.).

Sets blockchain_data and early_answer on state so the pipeline can stream
both the structured data card and a natural-language narration to the user.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

from ..state import RAGState

logger = logging.getLogger(__name__)


def make_blockchain_lookup_node(pipeline: Any):
    async def blockchain_lookup(state: RAGState) -> RAGState:
        from backend.services.blockchain_client import (
            LitecoinSpaceClient,
            format_litoshis,
            format_hashrate,
            format_share,
            BlockchainLookupType,
        )

        entity = state.get("matched_faq") or ""
        metadata: Dict[str, Any] = state.get("metadata") or {}
        query = state.get("sanitized_query") or state.get("raw_query") or ""

        redis_client = None
        if hasattr(pipeline, "get_redis_client"):
            try:
                redis_client = await pipeline.get_redis_client()
            except Exception:
                pass

        client = LitecoinSpaceClient(redis_client=redis_client)
        start = time.time()

        try:
            if entity.startswith("tx:"):
                txid = entity[3:]
                tx = await client.get_transaction(txid)
                total_output = sum(v.get("value", 0) for v in tx.vout)
                status_str = "Confirmed" if tx.status.confirmed else "Unconfirmed (in mempool)"
                confirmations = ""
                if tx.status.confirmed and tx.status.block_height:
                    try:
                        tip = await client.get_block_tip_height()
                        conf_count = tip - tx.status.block_height + 1
                        confirmations = f" ({conf_count:,} confirmations)"
                    except Exception:
                        pass

                answer = (
                    f"**Transaction {txid[:12]}...{txid[-8:]}**\n\n"
                    f"- **Status:** {status_str}{confirmations}\n"
                    f"- **Total Output:** {format_litoshis(total_output)}\n"
                    f"- **Fee:** {format_litoshis(tx.fee)}\n"
                    f"- **Size:** {tx.size:,} bytes (weight: {tx.weight:,})\n"
                    f"- **Inputs:** {len(tx.vin)} | **Outputs:** {len(tx.vout)}\n"
                )
                if tx.status.confirmed and tx.status.block_time:
                    dt = datetime.fromtimestamp(tx.status.block_time, tz=timezone.utc)
                    answer += f"- **Block:** {tx.status.block_height:,} ({dt.strftime('%Y-%m-%d %H:%M UTC')})\n"
                answer += f"\n[View on Litecoin Space]({tx.deep_link})"

                state["blockchain_data"] = tx.model_dump()
                state["blockchain_lookup_type"] = BlockchainLookupType.TRANSACTION.value

            elif entity.startswith("address:"):
                addr_str = entity[8:]
                addr = await client.get_address(addr_str)
                answer = (
                    f"**Address {addr_str[:10]}...{addr_str[-6:]}**\n\n"
                    f"- **Balance:** {format_litoshis(addr.balance_sat)}\n"
                    f"- **Total Received:** {format_litoshis(addr.chain_stats.funded_txo_sum)}\n"
                    f"- **Total Sent:** {format_litoshis(addr.chain_stats.spent_txo_sum)}\n"
                    f"- **Transactions:** {addr.total_tx_count:,}\n"
                )
                if addr.mempool_stats.tx_count > 0:
                    answer += f"- **Pending (mempool):** {addr.mempool_stats.tx_count} transaction(s)\n"
                answer += f"\n[View on Litecoin Space]({addr.deep_link})"

                state["blockchain_data"] = addr.model_dump()
                state["blockchain_lookup_type"] = BlockchainLookupType.ADDRESS.value

            elif entity.startswith("block_height:"):
                height = int(entity[13:])
                block = await client.get_block_by_height(height)
                dt = datetime.fromtimestamp(block.timestamp, tz=timezone.utc)
                answer = (
                    f"**Block {block.height:,}**\n\n"
                    f"- **Hash:** {block.id[:16]}...{block.id[-8:]}\n"
                    f"- **Timestamp:** {dt.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"- **Transactions:** {block.tx_count:,}\n"
                    f"- **Size:** {block.size:,} bytes\n"
                    f"- **Difficulty:** {block.difficulty:,.2f}\n"
                )
                answer += f"\n[View on Litecoin Space]({block.deep_link})"

                state["blockchain_data"] = block.model_dump()
                state["blockchain_lookup_type"] = BlockchainLookupType.BLOCK.value

            elif entity == "fees":
                fees = await client.get_recommended_fees()
                answer = (
                    "**Current Recommended Fees**\n\n"
                    f"- **Fastest (next block):** {fees.fastestFee} lit/vB\n"
                    f"- **Half Hour:** {fees.halfHourFee} lit/vB\n"
                    f"- **Hour:** {fees.hourFee} lit/vB\n"
                    f"- **Economy:** {fees.economyFee} lit/vB\n"
                    f"- **Minimum:** {fees.minimumFee} lit/vB\n"
                )

                state["blockchain_data"] = fees.model_dump()
                state["blockchain_lookup_type"] = BlockchainLookupType.FEES.value

            elif entity == "mempool":
                mempool = await client.get_mempool()
                vsize_mb = mempool.vsize / 1_000_000
                congestion = "Low" if vsize_mb < 1 else ("Moderate" if vsize_mb < 5 else "High")
                answer = (
                    "**Mempool Status**\n\n"
                    f"- **Unconfirmed Transactions:** {mempool.count:,}\n"
                    f"- **Total Size:** {vsize_mb:.2f} MB (vsize)\n"
                    f"- **Total Fees:** {format_litoshis(int(mempool.total_fee))}\n"
                    f"- **Congestion:** {congestion}\n"
                )

                state["blockchain_data"] = mempool.model_dump()
                state["blockchain_lookup_type"] = BlockchainLookupType.MEMPOOL.value

            elif entity == "hashrate":
                hr = await client.get_hashrate()
                diff = await client.get_difficulty_adjustment()
                answer = (
                    "**Litecoin Network Stats**\n\n"
                    f"- **Hashrate:** {format_hashrate(hr.current_hashrate)}\n"
                    f"- **Difficulty:** {hr.current_difficulty:,.2f}\n"
                    f"- **Next Adjustment:** {diff.progressPercent:.1f}% complete "
                    f"({diff.remainingBlocks:,} blocks remaining)\n"
                    f"- **Estimated Change:** {diff.difficultyChange:+.2f}%\n"
                )

                state["blockchain_data"] = {
                    "hashrate": hr.model_dump(),
                    "difficulty_adjustment": diff.model_dump(),
                }
                state["blockchain_lookup_type"] = BlockchainLookupType.HASHRATE.value

            elif entity == "mining_pools" or entity.startswith("mining_pools:"):
                period_key = "1w"
                api_period: str | None = "1w"
                if entity.startswith("mining_pools:"):
                    suffix = entity.split(":", 1)[1].strip()
                    if suffix == "all" or suffix == "":
                        period_key = "all"
                        api_period = None
                    else:
                        period_key = suffix
                        api_period = suffix
                data = await client.get_mining_pools(api_period)
                pools = data.get("pools") or []
                total_blocks = data.get("blockCount")
                last_est = data.get("lastEstimatedHashrate")
                period_label = period_key.upper() if len(period_key) <= 3 else period_key
                answer = f"**Mining pools** _(blocks in last {period_label}, from [Litecoin Space](https://litecoinspace.org))_\n\n"
                show = pools[:25]
                for p in show:
                    name = p.get("name", "?")
                    rank = p.get("rank", "")
                    blocks = p.get("blockCount", "")
                    slug = p.get("slug", "")
                    link = p.get("link") or ""
                    line = f"{rank}. **{name}** — {blocks:,} blocks" if isinstance(blocks, int) else f"{rank}. **{name}**"
                    if link:
                        line += f" — [site]({link})"
                    if slug:
                        line += f" _(slug `{slug}`)_"
                    answer += f"- {line}\n"
                if len(pools) > 25:
                    answer += f"\n_Showing top 25 of {len(pools)} pools._\n"
                if isinstance(total_blocks, int):
                    answer += f"\n**Total blocks** (window): {total_blocks:,}\n"
                if last_est is not None:
                    try:
                        answer += f"**Estimated network hashrate** (reference): {format_hashrate(float(last_est))}\n"
                    except (TypeError, ValueError):
                        pass
                state["blockchain_data"] = data
                state["blockchain_lookup_type"] = BlockchainLookupType.MINING_POOLS.value

            elif entity.startswith("mining_pool:"):
                slug = entity.split(":", 1)[1].strip()
                detail = await client.get_mining_pool_detail(slug)
                pool = (detail.get("pool") or {}) if isinstance(detail, dict) else {}
                if not pool:
                    state["early_answer"] = (
                        f"**Mining pool not found**\n\n"
                        f"No data for slug `{slug}` from Litecoin Space. "
                        f"Check the `slug` field in pool rankings (e.g. `f2pool`, `viabtc`)."
                    )
                    state["early_sources"] = []
                    state["early_cache_type"] = "blockchain_lookup_error"
                    metadata.update({
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "cache_hit": False,
                        "cache_type": "blockchain_lookup_error",
                        "intent": "blockchain_lookup",
                        "blockchain_entity": entity,
                        "blockchain_lookup_duration": time.time() - start,
                    })
                    state["metadata"] = metadata
                    return state
                name = pool.get("name", slug)
                link = pool.get("link") or ""
                bc = detail.get("blockCount") or {}
                bs = detail.get("blockShare") or {}
                est = detail.get("estimatedHashrate")
                rep = detail.get("reportedHashrate")
                answer = f"**{name}** _(mining pool)_\n\n"
                if link:
                    answer += f"- **Website:** {link}\n"
                if isinstance(est, (int, float)):
                    answer += f"- **Estimated hashrate:** {format_hashrate(float(est))}\n"
                if rep is not None:
                    try:
                        answer += f"- **Reported hashrate:** {format_hashrate(float(rep))}\n"
                    except (TypeError, ValueError):
                        answer += f"- **Reported hashrate:** {rep}\n"
                if isinstance(bc, dict):
                    answer += (
                        "- **Blocks found:** "
                        f"24h {bc.get('24h', 'n/a')}, 1w {bc.get('1w', 'n/a')}, "
                        f"all {bc.get('all', 'n/a')}\n"
                    )
                if isinstance(bs, dict):
                    answer += (
                        "- **Share of blocks:** "
                        f"24h {format_share(bs.get('24h'))}, 1w {format_share(bs.get('1w'))}, "
                        f"all {format_share(bs.get('all'))}\n"
                    )
                addrs = pool.get("addresses")
                if isinstance(addrs, list) and addrs:
                    preview = addrs[:3]
                    answer += f"- **Known coinbase addresses (sample):** {', '.join(preview)}\n"
                answer += "\n_Data from [Litecoin Space](https://litecoinspace.org) (weekly averages for hashrate series)._"
                state["blockchain_data"] = detail
                state["blockchain_lookup_type"] = BlockchainLookupType.MINING_POOL.value

            elif entity == "price":
                price = await client.get_price()
                age_label = ""
                if price.time > 0:
                    age_seconds = int(time.time()) - price.time
                    if age_seconds < 60:
                        age_label = "just now"
                    elif age_seconds < 3600:
                        age_label = f"{age_seconds // 60}m ago"
                    elif age_seconds < 86400:
                        age_label = f"{age_seconds // 3600}h ago"
                    else:
                        age_label = f"{age_seconds // 86400}d ago"
                header = "**Current Litecoin Price**"
                if age_label:
                    header += f" _(as of {age_label})_"
                answer = (
                    f"{header}\n\n"
                    f"- **USD:** ${price.USD:,.2f}\n"
                    f"- **EUR:** \u20ac{price.EUR:,.2f}\n"
                    f"- **GBP:** \u00a3{price.GBP:,.2f}\n"
                    f"- **AUD:** A${price.AUD:,.2f}\n"
                    f"- **JPY:** \u00a5{price.JPY:,.0f}\n"
                )

                state["blockchain_data"] = price.model_dump()
                state["blockchain_lookup_type"] = BlockchainLookupType.PRICE.value

            elif entity == "block_tip":
                tip_height = await client.get_block_tip_height()
                block = await client.get_block_by_height(tip_height)
                dt = datetime.fromtimestamp(block.timestamp, tz=timezone.utc)
                answer = (
                    f"**Current Block Height: {tip_height:,}**\n\n"
                    f"- **Hash:** {block.id[:16]}...{block.id[-8:]}\n"
                    f"- **Timestamp:** {dt.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"- **Transactions:** {block.tx_count:,}\n"
                    f"- **Size:** {block.size:,} bytes\n"
                    f"- **Difficulty:** {block.difficulty:,.2f}\n"
                )
                answer += f"\n[View on Litecoin Space]({block.deep_link})"

                state["blockchain_data"] = {**block.model_dump(), "tip_height": tip_height}
                state["blockchain_lookup_type"] = BlockchainLookupType.BLOCK_TIP.value

            else:
                logger.warning("Unknown blockchain entity: %s", entity)
                state["metadata"] = metadata
                return state

            state["early_answer"] = answer
            state["early_sources"] = []
            state["early_cache_type"] = "blockchain_lookup"
            metadata.update({
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "cache_hit": False,
                "cache_type": "blockchain_lookup",
                "intent": "blockchain_lookup",
                "blockchain_entity": entity,
                "blockchain_lookup_duration": time.time() - start,
            })

        except Exception as e:
            import httpx as _httpx

            logger.error("Blockchain lookup failed for %s: %s", entity, e, exc_info=True)

            if isinstance(e, _httpx.HTTPStatusError) and e.response.status_code == 404:
                if entity.startswith("tx:"):
                    answer = (
                        f"**Transaction not found**\n\n"
                        f"The transaction `{entity[3:12]}...{entity[-8:]}` was not found on the "
                        f"Litecoin blockchain. This may be a Bitcoin transaction ID, or the "
                        f"transaction may not exist yet.\n\n"
                        f"[Search on Litecoin Space](https://litecoinspace.org)"
                    )
                elif entity.startswith("address:"):
                    answer = (
                        f"**Address not found**\n\n"
                        f"The address `{entity[8:]}` was not found on the Litecoin blockchain."
                    )
                elif entity.startswith("block_height:") or entity.startswith("block_hash:"):
                    answer = (
                        f"**Block not found**\n\n"
                        f"The requested block was not found on the Litecoin blockchain. "
                        f"The current chain height may be lower than the requested block."
                    )
                elif entity.startswith("mining_pool:"):
                    slug = entity.split(":", 1)[1].strip()
                    answer = (
                        f"**Mining pool not found**\n\n"
                        f"No pool matched `{slug}` in the Litecoin Space mining index. "
                        f"Try the slug shown in [pool rankings](https://litecoinspace.org) "
                        f"(e.g. `f2pool`, `viabtc`)."
                    )
                else:
                    answer = "**Blockchain data unavailable**\n\nThe requested data could not be retrieved."
            else:
                answer = (
                    "**Blockchain lookup error**\n\n"
                    "Unable to fetch data from the Litecoin network right now. "
                    "Please try again in a moment."
                )

            state["early_answer"] = answer
            state["early_sources"] = []
            state["early_cache_type"] = "blockchain_lookup_error"

        state["metadata"] = metadata
        return state

    return blockchain_lookup
