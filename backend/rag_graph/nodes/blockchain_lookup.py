"""
Blockchain Lookup Node

Fetches live data from the Litecoin Space API when the intent classifier
detects a blockchain data query (transaction, address, block, fees, etc.).

Sets blockchain_data and early_answer on state so the pipeline can stream
both the structured data card and a natural-language narration to the user.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from ..state import RAGState

logger = logging.getLogger(__name__)

# Public Litecoin Space REST paths per lookup type. Rendered on live-data
# cards so a reader can see exactly which endpoint produced each number.
_ENDPOINT_BY_TYPE: Dict[str, str] = {
    "transaction": "/api/tx/{txid}",
    "address": "/api/address/{address}",
    "block": "/api/block/{hash}",
    "block_tip": "/api/blocks/tip/height",
    "fees": "/api/v1/fees/recommended",
    "mempool": "/api/mempool",
    "hashrate": "/api/v1/mining/hashrate/3d + /api/v1/difficulty-adjustment",
    "mining_pools": "/api/v1/mining/pools/{period}",
    "mining_pool": "/api/v1/mining/pool/{slug}",
    "price": "/api/v1/prices",
    # On-chain metrics come from litview.space (Litecoin Research Kit), not Litecoin Space.
    "metric": "/api/series/{series}/{index}",
}

SPACE_UNAVAILABLE_MESSAGE = (
    "**Live blockchain data is temporarily unavailable**\n\n"
    "The Litecoin Space API is not responding right now, so I can't fetch a "
    "current value. I won't guess at live numbers. Please try again in a minute, or "
    "check [Litecoin Space](https://litecoinspace.org) directly."
)

LITVIEW_UNAVAILABLE_MESSAGE = (
    "**On-chain metrics are temporarily unavailable**\n\n"
    "litview.space (the Litecoin Research Kit) is not responding right now, so I "
    "can't fetch a current value for this metric. I won't guess at live numbers. "
    "Please try again in a minute, or check [litview.space](https://litview.space) directly."
)


# Litecoin Space is still the source for anything that depends on its mempool
# or its block index. Probed 2026-10-06 against the co-hosted litview process
# (127.0.0.1:7070, the same brk that serves litview.space):
#   * fees and mempool are empty — getblocktemplate is called without the
#     mweb and segwit rules, so the template update fails
#   * /api/blocks/tip/height stops at 2026-09-12; a recent height 404s
#   * mining pools and /v1/mining/hashrate describe that same stale index
#   * /v1/difficulty-adjustment's next retarget height is already in the past
# Spot USD (/api/v1/prices) and the day1 series hash_rate and difficulty are
# current, and they answer in a few milliseconds on the local port.
_HASHRATE_ADJUSTMENT_TIMEOUT_S = float(os.getenv("LITECOIN_SPACE_ADJUSTMENT_TIMEOUT", "4"))
_SPACE_PRICE_TIMEOUT_S = float(os.getenv("LITECOIN_SPACE_PRICE_TIMEOUT", "4"))

_FIAT_LINES = (
    ("USD", lambda v: f"${v:,.2f}"),
    ("EUR", lambda v: f"€{v:,.2f}"),
    ("GBP", lambda v: f"£{v:,.2f}"),
    ("AUD", lambda v: f"A${v:,.2f}"),
    ("JPY", lambda v: f"¥{v:,.0f}"),
)


def _positive(value: Any) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    return num


def _stamp_provenance(
    data: Any,
    lookup_type: str,
    source: str = "Litecoin Space",
    endpoint: Optional[str] = None,
) -> Any:
    """Attach `_provenance` (fetched_at, endpoint, source) to a card payload."""
    if not isinstance(data, dict):
        return data
    stamped = dict(data)
    stamped["_provenance"] = {
        "source": source,
        "endpoint": endpoint or _ENDPOINT_BY_TYPE.get(lookup_type, "/api"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return stamped


async def _litview_spot(redis_client: Any) -> Optional[Dict[str, Any]]:
    from backend.services.litview_client import LitviewClient

    client = LitviewClient(redis_client=redis_client)
    try:
        return await client.get_spot_price()
    finally:
        await client.close()


async def _litview_hashrate_difficulty(redis_client: Any) -> Tuple[Optional[float], Optional[float]]:
    from backend.services.litview_client import LitviewClient

    client = LitviewClient(redis_client=redis_client)
    try:
        hashrate, difficulty = await asyncio.gather(
            client.get_latest("hash_rate", "day1"),
            client.get_latest("difficulty", "day1"),
        )
        return hashrate, difficulty
    finally:
        await client.close()


def _fiat_lines(values: Dict[str, Any]) -> str:
    lines = []
    for code, fmt in _FIAT_LINES:
        num = _positive(values.get(code))
        if num is not None:
            lines.append(f"- **{code}:** {fmt(num)}")
    return "\n".join(lines)


def _age_label(unix_time: int) -> str:
    if unix_time <= 0:
        return ""
    age_seconds = int(time.time()) - unix_time
    if age_seconds < 60:
        return "just now"
    if age_seconds < 3600:
        return f"{age_seconds // 60}m ago"
    if age_seconds < 86400:
        return f"{age_seconds // 3600}h ago"
    return f"{age_seconds // 86400}d ago"


def _finish_early(
    state: RAGState,
    metadata: Dict[str, Any],
    *,
    answer: str,
    entity: str,
    cache_type: str,
    start: float,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> RAGState:
    """Common tail for live lookups: early answer, no sources, lookup metadata."""
    state["early_answer"] = answer
    state["early_sources"] = []
    state["early_cache_type"] = cache_type
    metadata.update({
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "cache_hit": False,
        "cache_type": cache_type,
        "intent": "blockchain_lookup",
        "blockchain_entity": entity,
        "blockchain_lookup_duration": time.time() - start,
    })
    if extra_metadata:
        metadata.update(extra_metadata)
    state["metadata"] = metadata
    return state


def _fmt_as_of(ts: Optional[int]) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


async def _metric_lookup(
    entity: str,
    state: RAGState,
    metadata: Dict[str, Any],
    redis_client: Any,
    start: float,
) -> RAGState:
    """
    `metric:<id>` -> litview.space series snapshot rendered as a MetricCard.

    Three honest outcomes:
      ok            value + sparkline + % changes
      not_computed  litview has not computed this series up to now (say so, no guess)
      error         litview unreachable / series missing (tool-down message)
    Results are never written to the answer caches (same rule as other live cards).
    """
    import httpx as _httpx

    from backend.services.circuit_breaker import CircuitOpen
    from backend.services.litview_client import (
        LITVIEW_CHART_URL,
        LitviewClient,
        LitviewError,
        MetricNotComputed,
        format_metric_value,
        format_pct_change,
    )
    from backend.services.metrics_registry import get_registry

    metric_id = entity.split(":", 1)[1].strip()
    spec = get_registry().get(metric_id)
    if spec is None:
        logger.warning("Unknown metric id in entity: %s", entity)
        return _finish_early(
            state, metadata, entity=entity, start=start, cache_type="blockchain_lookup_error",
            answer="**Unknown metric**\n\nI don't have that on-chain metric wired up yet.",
        )

    chart_url = spec.chart_url or LITVIEW_CHART_URL
    endpoint = _ENDPOINT_BY_TYPE["metric"].format(series=spec.series, index=spec.index)
    base_card: Dict[str, Any] = {
        "metric_id": spec.id,
        "label": spec.label,
        "unit": spec.unit,
        "series": spec.series,
        "index": spec.index,
        "description": spec.description,
        "chart_url": chart_url,
    }

    client = LitviewClient(redis_client=redis_client)
    try:
        try:
            snap = await client.get_metric_snapshot(
                spec.series, spec.index, points=spec.spark_points, change_windows=spec.change_windows
            )
        except MetricNotComputed as nc:
            computed_h = f"{nc.computed_height:,}" if nc.computed_height else "an earlier height"
            tip_h = f"{nc.tip_height:,}" if nc.tip_height else "the current tip"
            through = f" ({nc.computed_at})" if nc.computed_at else ""
            answer = (
                f"**{spec.label}: not computed yet on litview.space**\n\n"
                f"{spec.description}\n\n"
                f"litview.space has indexed the Litecoin chain to block {tip_h} but has only "
                f"computed this series through block {computed_h}{through}, so there is no current "
                f"value to report and I won't estimate one. Check back later or "
                f"[explore the series on litview.space]({chart_url})."
            )
            card = {
                **base_card,
                "status": "not_computed",
                "value": None,
                "value_formatted": None,
                "as_of": None,
                "points": [],
                "changes": {},
                "computed_height": nc.computed_height,
                "computed_at": nc.computed_at,
                "tip_height": nc.tip_height,
            }
            state["blockchain_data"] = _stamp_provenance(card, "metric", source="litview.space", endpoint=endpoint)
            state["blockchain_lookup_type"] = "metric"
            return _finish_early(
                state, metadata, entity=entity, start=start, cache_type="blockchain_lookup",
                answer=answer, extra_metadata={"metric_status": "not_computed"},
            )

        value_fmt = format_metric_value(snap.value, spec.unit)
        as_of = _fmt_as_of(snap.as_of)
        header = f"**{spec.label}: {value_fmt}**" + (f" _(as of {as_of} UTC)_" if as_of else "")
        lines = [header, "", spec.description, ""]
        for w in spec.change_windows:
            unit_word = "day" if spec.index == "day1" else spec.index
            lines.append(f"- **{w}-{unit_word} change:** {format_pct_change(snap.changes_pct.get(w))}")
        lines.append("")
        lines.append(f"Data from [litview.space]({chart_url}) (Litecoin Research Kit).")
        answer = "\n".join(lines)

        card = {
            **base_card,
            "status": "ok",
            "value": snap.value,
            "value_formatted": value_fmt,
            "as_of": snap.as_of,
            "points": [{"t": p.t, "v": p.v} for p in snap.points],
            "changes": {str(w): snap.changes_pct.get(w) for w in spec.change_windows},
            "stamp": snap.stamp,
        }
        state["blockchain_data"] = _stamp_provenance(card, "metric", source="litview.space", endpoint=endpoint)
        state["blockchain_lookup_type"] = "metric"
        return _finish_early(
            state, metadata, entity=entity, start=start, cache_type="blockchain_lookup",
            answer=answer, extra_metadata={"metric_status": "ok"},
        )

    except Exception as e:  # noqa: BLE001
        logger.error("Metric lookup failed for %s: %s", entity, e, exc_info=True)
        try:
            from backend.monitoring.metrics import tool_error_total

            tool_error_total.labels(tool="litview").inc()
        except Exception:
            pass

        is_down = isinstance(e, (CircuitOpen, _httpx.ConnectError, _httpx.TimeoutException)) or (
            isinstance(e, _httpx.HTTPStatusError) and e.response.status_code >= 500
        )
        if is_down:
            answer = LITVIEW_UNAVAILABLE_MESSAGE
            metadata["tool_unavailable"] = "litview"
        elif isinstance(e, LitviewError):
            answer = (
                f"**{spec.label} unavailable**\n\n"
                f"litview.space did not recognise the series `{spec.series}` ({spec.index}) right now, "
                f"so I can't report a value. You can [browse litview.space]({chart_url}) directly."
            )
        else:
            answer = (
                "**On-chain metric lookup error**\n\n"
                "Unable to fetch this metric from litview.space right now. Please try again in a moment."
            )
        return _finish_early(
            state, metadata, entity=entity, start=start, cache_type="blockchain_lookup_error",
            answer=answer, extra_metadata={"metric_status": "error"},
        )
    finally:
        try:
            await client.close()
        except Exception:
            pass


def make_blockchain_lookup_node(pipeline: Any):
    async def blockchain_lookup(state: RAGState) -> RAGState:
        from backend.services.blockchain_client import (
            BlockchainLookupType,
            HashrateData,
            LitecoinSpaceClient,
            format_hashrate,
            format_litoshis,
            format_share,
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

        start = time.time()

        # On-chain metrics are served by litview.space, not Litecoin Space.
        if entity.startswith("metric:"):
            return await _metric_lookup(entity, state, metadata, redis_client, start)

        client = LitecoinSpaceClient(redis_client=redis_client)

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
                # Daily series on litview match today's difficulty and are
                # local. The Space mining-hashrate route describes litview's
                # stale block index, so it is only the fallback.
                basis = "3d"
                source = "Litecoin Space"
                endpoint = "/api/v1/mining/hashrate/3d"
                hr = None
                try:
                    series_hr, series_diff = await _litview_hashrate_difficulty(redis_client)
                    if _positive(series_hr) and _positive(series_diff):
                        hr = HashrateData(
                            current_hashrate=float(series_hr),
                            current_difficulty=float(series_diff),
                        )
                        basis = "daily"
                        source = "litview.space"
                        endpoint = "/api/series/hash_rate/day1/latest"
                except Exception as exc:
                    logger.info("litview hashrate series unavailable: %s", exc)
                if hr is None:
                    hr = await client.get_hashrate()

                diff = None
                try:
                    diff = await asyncio.wait_for(
                        client.get_difficulty_adjustment(),
                        timeout=_HASHRATE_ADJUSTMENT_TIMEOUT_S,
                    )
                except Exception as exc:
                    logger.info("difficulty adjustment unavailable: %s", exc)
                if diff is not None and source == "litview.space":
                    endpoint += " · adjustment litecoinspace.org/api/v1/difficulty-adjustment"

                basis_label = "daily estimate" if basis == "daily" else "3-day estimate"
                answer = (
                    "**Litecoin Network Stats**\n\n"
                    f"- **Hashrate:** {format_hashrate(hr.current_hashrate)} ({basis_label})\n"
                    f"- **Difficulty:** {hr.current_difficulty:,.2f}\n"
                )
                if diff is not None:
                    answer += (
                        f"- **Next Adjustment:** {diff.progressPercent:.1f}% complete "
                        f"({diff.remainingBlocks:,} blocks remaining)\n"
                        f"- **Estimated Change:** {diff.difficultyChange:+.2f}%\n"
                    )
                else:
                    answer += "- **Next adjustment:** not available from Litecoin Space right now\n"

                payload: Dict[str, Any] = {"hashrate": {**hr.model_dump(), "basis": basis}}
                if diff is not None:
                    payload["difficulty_adjustment"] = diff.model_dump()
                state["blockchain_data"] = _stamp_provenance(
                    payload, "hashrate", source=source, endpoint=endpoint
                )
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
                state["blockchain_data"] = {**data, "period": period_key} if isinstance(data, dict) else data
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
                # USD from local litview (fresh, ~1ms). Other currencies stay
                # on Litecoin Space, which publishes a full fiat basket.
                # litview's /v1/historical-price is oldest-first, so it is not
                # a drop-in for get_price().
                spot: Optional[Dict[str, Any]] = None
                space_price = None
                try:
                    spot = await asyncio.wait_for(_litview_spot(redis_client), timeout=4.0)
                except Exception as exc:
                    logger.info("litview spot price unavailable: %s", exc)
                try:
                    space_price = await asyncio.wait_for(
                        client.get_spot_prices(), timeout=_SPACE_PRICE_TIMEOUT_S
                    )
                except Exception as exc:
                    logger.info("Litecoin Space price unavailable: %s", exc)

                values: Dict[str, Any] = {}
                quote_time = 0
                source = "Litecoin Space"
                endpoint = "/api/v1/prices"
                if spot and _positive(spot.get("USD")):
                    values["USD"] = float(spot["USD"])
                    quote_time = int(spot.get("time") or 0)
                    source = "litview.space"
                    endpoint = "/api/v1/prices"
                elif space_price is not None and _positive(space_price.USD):
                    values["USD"] = float(space_price.USD)
                    quote_time = int(space_price.time or 0)
                if space_price is not None:
                    for code in ("EUR", "GBP", "AUD", "JPY"):
                        num = _positive(getattr(space_price, code, None))
                        if num is not None:
                            values[code] = num
                    if source == "litview.space" and any(code in values for code in ("EUR", "GBP", "AUD", "JPY")):
                        endpoint = "/api/v1/prices · FX litecoinspace.org/api/v1/prices"
                    if quote_time <= 0:
                        quote_time = int(space_price.time or 0)
                if not values:
                    raise TimeoutError("no live price from litview or Litecoin Space")

                header = "**Current Litecoin Price**"
                age = _age_label(quote_time)
                if age:
                    header += f" _(as of {age})_"
                answer = f"{header}\n\n{_fiat_lines(values)}\n"
                card = {"time": quote_time, **values}
                state["blockchain_data"] = _stamp_provenance(
                    card, "price", source=source, endpoint=endpoint
                )
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

            lookup_type = state.get("blockchain_lookup_type") or ""
            existing = state.get("blockchain_data")
            if not (isinstance(existing, dict) and existing.get("_provenance")):
                state["blockchain_data"] = _stamp_provenance(existing, lookup_type)

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
            from backend.services.circuit_breaker import CircuitOpen

            logger.error("Blockchain lookup failed for %s: %s", entity, e, exc_info=True)
            try:
                from backend.monitoring.metrics import tool_error_total

                tool_error_total.labels(tool="litecoin_space").inc()
            except Exception:
                pass

            if isinstance(e, (CircuitOpen, _httpx.ConnectError, _httpx.TimeoutException)):
                # Tool is down: say so plainly rather than offering a vague retry.
                answer = SPACE_UNAVAILABLE_MESSAGE
                metadata["tool_unavailable"] = "litecoin_space"
            elif isinstance(e, _httpx.HTTPStatusError) and e.response.status_code == 404:
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
            # Still a look-up (the tool failed, retrieval was never the plan); keep the
            # intent on metadata so logs and the golden-set scorer classify it correctly.
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

    return blockchain_lookup
