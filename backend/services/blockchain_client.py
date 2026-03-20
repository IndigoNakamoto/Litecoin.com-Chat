"""
Litecoin Space Blockchain API Client

Async HTTP client for the Litecoin Space (mempool.space fork) REST API.
All blockchain data lookups are proxied through this client to enforce
rate limiting, caching, and consistent error handling.

Endpoint reference: https://litecoinspace.org/docs/api — REST paths under
`/api` and `/api/v1` (difficulty, address, block, tx, mempool, fees,
mining, lightning, …). This module implements the subset used by RAG
live lookup; add thin `get_*` methods plus intent routing for more.
"""

from __future__ import annotations

import json
import logging
import os
import time
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LITECOIN_SPACE_API_URL = os.getenv(
    "LITECOIN_SPACE_API_URL", "https://litecoinspace.org/api"
).rstrip("/")

LITECOIN_SPACE_EXPLORER_URL = os.getenv(
    "LITECOIN_SPACE_EXPLORER_URL", "https://litecoinspace.org"
).rstrip("/")

CACHE_TTL_VOLATILE = int(os.getenv("LITECOIN_SPACE_CACHE_TTL", "150"))
CACHE_TTL_IMMUTABLE = 3600
CACHE_KEY_PREFIX = "ltcspace:"


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class TransactionStatus(BaseModel):
    confirmed: bool = False
    block_height: Optional[int] = None
    block_hash: Optional[str] = None
    block_time: Optional[int] = None


class TransactionData(BaseModel):
    txid: str
    version: int = 0
    locktime: int = 0
    size: int = 0
    weight: int = 0
    fee: int = 0
    status: TransactionStatus = Field(default_factory=TransactionStatus)
    vin: List[Dict[str, Any]] = Field(default_factory=list)
    vout: List[Dict[str, Any]] = Field(default_factory=list)
    deep_link: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.deep_link:
            self.deep_link = f"{LITECOIN_SPACE_EXPLORER_URL}/tx/{self.txid}"


class AddressStats(BaseModel):
    funded_txo_count: int = 0
    funded_txo_sum: int = 0
    spent_txo_count: int = 0
    spent_txo_sum: int = 0
    tx_count: int = 0


class AddressData(BaseModel):
    address: str
    chain_stats: AddressStats = Field(default_factory=AddressStats)
    mempool_stats: AddressStats = Field(default_factory=AddressStats)
    deep_link: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.deep_link:
            self.deep_link = f"{LITECOIN_SPACE_EXPLORER_URL}/address/{self.address}"

    @property
    def balance_sat(self) -> int:
        funded = self.chain_stats.funded_txo_sum + self.mempool_stats.funded_txo_sum
        spent = self.chain_stats.spent_txo_sum + self.mempool_stats.spent_txo_sum
        return funded - spent

    @property
    def total_tx_count(self) -> int:
        return self.chain_stats.tx_count + self.mempool_stats.tx_count


class BlockData(BaseModel):
    id: str = ""
    height: int = 0
    version: int = 0
    timestamp: int = 0
    tx_count: int = 0
    size: int = 0
    weight: int = 0
    merkle_root: str = ""
    previousblockhash: str = ""
    nonce: int = 0
    bits: int = 0
    difficulty: float = 0.0
    deep_link: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.deep_link and self.id:
            self.deep_link = f"{LITECOIN_SPACE_EXPLORER_URL}/block/{self.id}"


class FeeData(BaseModel):
    fastestFee: int = 0
    halfHourFee: int = 0
    hourFee: int = 0
    economyFee: int = 0
    minimumFee: int = 0


class MempoolData(BaseModel):
    count: int = 0
    vsize: int = 0
    total_fee: float = 0.0


class HashrateData(BaseModel):
    current_hashrate: float = 0.0
    current_difficulty: float = 0.0


class DifficultyAdjustment(BaseModel):
    progressPercent: float = 0.0
    difficultyChange: float = 0.0
    estimatedRetargetDate: int = 0
    remainingBlocks: int = 0
    remainingTime: int = 0
    previousRetarget: float = 0.0
    nextRetargetHeight: int = 0


class PriceData(BaseModel):
    model_config = {"extra": "ignore"}
    time: int = 0
    USD: float = 0.0
    EUR: float = 0.0
    GBP: float = 0.0
    AUD: float = 0.0
    JPY: float = 0.0


class BlockchainLookupType(str, Enum):
    TRANSACTION = "transaction"
    ADDRESS = "address"
    BLOCK = "block"
    BLOCK_TIP = "block_tip"
    FEES = "fees"
    MEMPOOL = "mempool"
    HASHRATE = "hashrate"
    MINING_POOLS = "mining_pools"
    MINING_POOL = "mining_pool"
    PRICE = "price"
    DIFFICULTY = "difficulty"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LitecoinSpaceClient:
    """Async client for the Litecoin Space REST API with Redis caching."""

    def __init__(self, redis_client=None):
        self._http = httpx.AsyncClient(
            base_url=LITECOIN_SPACE_API_URL,
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._redis = redis_client

    async def close(self):
        await self._http.aclose()

    # -- Cache helpers -------------------------------------------------------

    async def _cache_get(self, key: str) -> Optional[str]:
        if not self._redis:
            return None
        try:
            val = await self._redis.get(f"{CACHE_KEY_PREFIX}{key}")
            return val
        except Exception as e:
            logger.debug("Redis cache read failed for %s: %s", key, e)
            return None

    async def _cache_set(self, key: str, value: str, ttl: int) -> None:
        if not self._redis:
            return
        try:
            await self._redis.set(f"{CACHE_KEY_PREFIX}{key}", value, ex=ttl)
        except Exception as e:
            logger.debug("Redis cache write failed for %s: %s", key, e)

    # -- HTTP helper ---------------------------------------------------------

    async def _request(self, path: str) -> httpx.Response:
        """GET with basic retry on 429. Returns the raw Response."""
        for attempt in range(3):
            resp = await self._http.get(path)
            if resp.status_code == 429:
                wait = min(2 ** attempt, 8)
                logger.warning("Litecoin Space rate limited, retrying in %ds", wait)
                import asyncio
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        raise httpx.HTTPStatusError(
            "Rate limited after retries",
            request=resp.request,  # type: ignore[possibly-undefined]
            response=resp,  # type: ignore[possibly-undefined]
        )

    async def _get(self, path: str) -> Any:
        """GET returning parsed JSON (object or array)."""
        resp = await self._request(path)
        return resp.json()

    async def _get_text(self, path: str) -> str:
        """GET returning raw response text (for endpoints that return plain strings)."""
        resp = await self._request(path)
        return resp.text.strip()

    async def _cached_get(self, cache_key: str, path: str, ttl: int) -> Any:
        cached = await self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return json.loads(cached)
        data = await self._get(path)
        await self._cache_set(cache_key, json.dumps(data), ttl)
        return data

    # -- Public API ----------------------------------------------------------

    async def get_transaction(self, txid: str) -> TransactionData:
        cache_key = f"tx:{txid}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            data = json.loads(cached)
        else:
            data = await self._get(f"/tx/{txid}")
        tx = TransactionData.model_validate(data)
        ttl = CACHE_TTL_IMMUTABLE if tx.status.confirmed else CACHE_TTL_VOLATILE
        await self._cache_set(cache_key, json.dumps(data), ttl)
        return tx

    async def get_address(self, address: str) -> AddressData:
        data = await self._cached_get(
            f"addr:{address}", f"/address/{address}", CACHE_TTL_VOLATILE
        )
        return AddressData.model_validate(data)

    async def get_block_by_hash(self, block_hash: str) -> BlockData:
        data = await self._cached_get(
            f"block:{block_hash}", f"/block/{block_hash}", CACHE_TTL_IMMUTABLE
        )
        return BlockData.model_validate(data)

    async def get_block_by_height(self, height: int) -> BlockData:
        cache_key = f"blockheight:{height}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            block_hash = cached
        else:
            block_hash = await self._get_text(f"/block-height/{height}")
            await self._cache_set(cache_key, block_hash, CACHE_TTL_IMMUTABLE)
        return await self.get_block_by_hash(block_hash)

    async def get_recommended_fees(self) -> FeeData:
        data = await self._cached_get(
            "fees:recommended", "/v1/fees/recommended", CACHE_TTL_VOLATILE
        )
        return FeeData.model_validate(data)

    async def get_mempool(self) -> MempoolData:
        data = await self._cached_get(
            "mempool", "/mempool", CACHE_TTL_VOLATILE
        )
        return MempoolData.model_validate(data)

    async def get_hashrate(self) -> HashrateData:
        data = await self.get_mining_network_hashrate_detail("1w")
        current = data.get("currentHashrate", 0)
        difficulty = data.get("currentDifficulty", 0)
        return HashrateData(current_hashrate=current, current_difficulty=difficulty)

    async def get_difficulty_adjustment(self) -> DifficultyAdjustment:
        data = await self._cached_get(
            "difficulty", "/v1/difficulty-adjustment", CACHE_TTL_VOLATILE
        )
        return DifficultyAdjustment.model_validate(data)

    async def get_price(self) -> PriceData:
        data = await self._cached_get(
            "prices", "/v1/historical-price", CACHE_TTL_VOLATILE
        )
        prices_list = data.get("prices", [])
        if not prices_list:
            return PriceData()
        latest = prices_list[0]
        return PriceData.model_validate(latest)

    async def get_block_tip_height(self) -> int:
        cache_key = "tip:height"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return int(cached)
        text = await self._get_text("/blocks/tip/height")
        await self._cache_set(cache_key, text, CACHE_TTL_VOLATILE)
        return int(text)

    async def get_mining_pools(self, time_period: Optional[str] = "1w") -> Dict[str, Any]:
        """
        GET /v1/mining/pools[/:timePeriod] — pool rankings by blocks found.

        time_period: one of 24h, 3d, 1w, 1m, 3m, 6m, 1y, 2y, 3y; None or '' for full history.
        """
        path = "/v1/mining/pools"
        if time_period:
            path = f"{path}/{time_period}"
        ck = f"mining:pools:{time_period or 'all'}"
        data = await self._cached_get(ck, path, CACHE_TTL_VOLATILE)
        if not isinstance(data, dict):
            return {}
        return data

    async def get_mining_pool_detail(self, slug: str) -> Dict[str, Any]:
        """GET /v1/mining/pool/:slug — pool metadata, block counts/shares, estimated hashrate."""
        slug = slug.strip().lower()
        return await self._cached_get(
            f"mining:pool:{slug}",
            f"/v1/mining/pool/{slug}",
            CACHE_TTL_VOLATILE,
        )

    async def get_mining_pool_hashrates(
        self, time_period: Optional[str] = "1m"
    ) -> List[Dict[str, Any]]:
        """
        GET /v1/mining/hashrate/pools[/:timePeriod] — pool hashrate leaderboard.

        time_period: 1m, 3m, 6m, 1y, 2y, 3y, or None/'' for all available.
        """
        path = "/v1/mining/hashrate/pools"
        if time_period:
            path = f"{path}/{time_period}"
        ck = f"mining:hr:pools:{time_period or 'all'}"
        data = await self._cached_get(ck, path, CACHE_TTL_VOLATILE)
        if isinstance(data, list):
            return data
        return []

    async def get_mining_network_hashrate_detail(
        self, time_period: Optional[str] = "1w"
    ) -> Dict[str, Any]:
        """GET /v1/mining/hashrate[/:timePeriod] — full network hashrate/difficulty payload."""
        path = "/v1/mining/hashrate"
        if time_period:
            path = f"{path}/{time_period}"
        ck = f"mining:hashrate:{time_period or 'all'}"
        data = await self._cached_get(ck, path, CACHE_TTL_VOLATILE)
        return data if isinstance(data, dict) else {}


def data_is_confirmed(data: Any) -> bool:
    """Check if raw transaction JSON indicates confirmation."""
    if isinstance(data, dict):
        status = data.get("status", {})
        if isinstance(status, dict):
            return status.get("confirmed", False)
    return False


def format_litoshis(litoshis: int) -> str:
    """Convert litoshis to LTC string."""
    return f"{litoshis / 1e8:.8f} LTC"


def format_hashrate(hashrate_hs: float) -> str:
    """Format hashrate from H/s to human-readable."""
    if hashrate_hs >= 1e18:
        return f"{hashrate_hs / 1e18:.2f} EH/s"
    if hashrate_hs >= 1e15:
        return f"{hashrate_hs / 1e15:.2f} PH/s"
    if hashrate_hs >= 1e12:
        return f"{hashrate_hs / 1e12:.2f} TH/s"
    if hashrate_hs >= 1e9:
        return f"{hashrate_hs / 1e9:.2f} GH/s"
    return f"{hashrate_hs:.0f} H/s"


def format_share(fraction: Optional[float]) -> str:
    """Format block-share / hashrate share (0–1) as a percentage string."""
    if fraction is None:
        return "n/a"
    try:
        return f"{float(fraction) * 100:.2f}%"
    except (TypeError, ValueError):
        return "n/a"
