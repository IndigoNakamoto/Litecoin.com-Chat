"""
litview.space (Litecoin Research Kit) Series API client.

litview is the hosted instance of LRK: on-chain analytics with ~56k time-series
(price, supply, MVRV, realized price, SOPR, ...). No auth, no rate limit.
OpenAPI: https://litview.space/openapi.json

Endpoints used:
  GET /api/series/{series}                  -> {"indexes": [...], "type": "..."}
  GET /api/series/{series}/{index}/latest   -> bare value, or `null`
  GET /api/series/bulk?series=a,b&index=..&start=-N
                                            -> [{"index","type","start","end","stamp","data":[...]}, ...]
  GET /api/series/search?q=..&limit=..      -> ["series_name", ...]
  GET /api/server/sync                      -> {"indexed_height","computed_height","tip_height",...}

Two facts drive the design:
  * `timestamp` is itself a series on every time index, so one bulk call for
    `timestamp,<series>` yields aligned (t, v) points for a sparkline.
  * Computed series can be `null` past `computed_height` (the hosted instance
    was ~3 years behind on computed metrics when this was written). That is a
    first-class state here (`MetricNotComputed`), never a zero.

Errors come back as structured JSON:
  {"error": {"type": "not_found", "code": "series_not_found", "message": "..."}}
  codes seen: series_not_found, series_unsupported_index, no_data
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Public site. Also the fallback when LITVIEW_API_URL points at the co-hosted
# process (http://host.docker.internal:7070) and that process is down.
LITVIEW_PUBLIC_URL = "https://litview.space"
LITVIEW_API_URL = os.getenv("LITVIEW_API_URL", LITVIEW_PUBLIC_URL).rstrip("/")
LITVIEW_CHART_URL = os.getenv("LITVIEW_CHART_URL", LITVIEW_PUBLIC_URL).rstrip("/")
LITVIEW_TIMEOUT_SECONDS = float(os.getenv("LITVIEW_TIMEOUT_SECONDS", "10"))

CACHE_KEY_PREFIX = "litview:"
# Cache TTLs (seconds) by what is being cached.
TTL_LATEST = int(os.getenv("LITVIEW_CACHE_TTL_LATEST", "600"))
TTL_SYNC = int(os.getenv("LITVIEW_CACHE_TTL_SYNC", "300"))
TTL_META = int(os.getenv("LITVIEW_CACHE_TTL_META", str(6 * 3600)))
_TTL_RANGE_BY_INDEX = {
    "minute10": 300, "minute30": 300, "hour1": 600, "hour4": 1200, "hour12": 1800,
    "day1": 3600, "day3": 3 * 3600, "week1": 6 * 3600, "month1": 6 * 3600,
    "month3": 12 * 3600, "month6": 12 * 3600, "year1": 24 * 3600, "year10": 24 * 3600,
}


def range_ttl(index: str) -> int:
    return _TTL_RANGE_BY_INDEX.get(index, 3600)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LitviewError(Exception):
    """Base class for litview failures that are *not* transport problems."""


class LitviewSeriesNotFound(LitviewError):
    def __init__(self, series: str, message: str = ""):
        super().__init__(message or f"series {series!r} not found")
        self.series = series


class LitviewUnsupportedIndex(LitviewError):
    def __init__(self, series: str, index: str, message: str = ""):
        super().__init__(message or f"series {series!r} does not support index {index!r}")
        self.series = series
        self.index = index


class MetricNotComputed(LitviewError):
    """
    litview has indexed the chain but has not (yet) computed this series up to
    the present. Carries how far computation has got so the bot can say so.
    """

    def __init__(
        self,
        series: str,
        index: str,
        computed_height: Optional[int] = None,
        computed_at: Optional[str] = None,
        tip_height: Optional[int] = None,
    ):
        super().__init__(f"series {series!r} ({index}) has no computed value yet")
        self.series = series
        self.index = index
        self.computed_height = computed_height
        self.computed_at = computed_at
        self.tip_height = tip_height


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class SyncStatus:
    indexed_height: Optional[int] = None
    computed_height: Optional[int] = None
    tip_height: Optional[int] = None
    blocks_behind: Optional[int] = None
    last_indexed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SeriesInfo:
    series: str
    indexes: List[str] = field(default_factory=list)
    type: str = ""


@dataclass
class SeriesPoint:
    t: Optional[int]  # unix seconds (None if the timestamp series had a gap)
    v: Optional[float]


@dataclass
class SeriesRange:
    series: str
    index: str
    points: List[SeriesPoint] = field(default_factory=list)
    stamp: Optional[str] = None
    version: Optional[int] = None

    @property
    def last_non_null(self) -> Optional[SeriesPoint]:
        for p in reversed(self.points):
            if p.v is not None:
                return p
        return None

    def all_null(self) -> bool:
        return all(p.v is None for p in self.points)


@dataclass
class MetricSnapshot:
    series: str
    index: str
    value: float
    as_of: Optional[int]  # unix seconds of the value's bucket
    points: List[SeriesPoint]
    changes_pct: Dict[int, Optional[float]]  # window (points back) -> % change
    stamp: Optional[str] = None
    endpoint: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def _coerce_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100.0


class LitviewClient:
    """Async client for the litview Series API with Redis caching + breaker."""

    def __init__(self, redis_client=None, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = (base_url or LITVIEW_API_URL).rstrip("/")
        self._timeout = timeout or LITVIEW_TIMEOUT_SECONDS
        self._http = self._open_http(self.base_url)
        self._redis = redis_client
        self._fallback_lock = asyncio.Lock()

    def _open_http(self, base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(self._timeout, connect=3.0),
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "litecoin-knowledge-hub/1.0"},
        )

    async def _failover_to_public(self) -> bool:
        """Switch this client to the public site after the local process refuses a connection."""
        async with self._fallback_lock:
            if self.base_url == LITVIEW_PUBLIC_URL:
                return False
            logger.warning("litview at %s is unreachable; using %s", self.base_url, LITVIEW_PUBLIC_URL)
            old = self._http
            self.base_url = LITVIEW_PUBLIC_URL
            self._http = self._open_http(LITVIEW_PUBLIC_URL)
            try:
                await old.aclose()
            except Exception:  # noqa: BLE001
                pass
            return True

    async def close(self) -> None:
        await self._http.aclose()

    # -- cache ---------------------------------------------------------------

    async def _cache_get(self, key: str) -> Optional[Any]:
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(CACHE_KEY_PREFIX + key)
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            logger.debug("litview cache read failed for %s: %s", key, e)
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        if not self._redis:
            return
        try:
            await self._redis.set(CACHE_KEY_PREFIX + key, json.dumps(value), ex=max(1, int(ttl)))
        except Exception as e:  # noqa: BLE001
            logger.debug("litview cache write failed for %s: %s", key, e)

    # -- http ----------------------------------------------------------------

    @staticmethod
    def _raise_structured(body: Any, series: str = "", index: str = "") -> None:
        err = body.get("error") if isinstance(body, dict) else None
        if not isinstance(err, dict):
            return
        code = err.get("code") or ""
        msg = err.get("message") or ""
        if code == "series_not_found":
            raise LitviewSeriesNotFound(series, msg)
        if code == "series_unsupported_index":
            raise LitviewUnsupportedIndex(series, index, msg)
        raise LitviewError(msg or code or "litview error")

    async def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None,
                        series: str = "", index: str = "") -> Any:
        from backend.services.circuit_breaker import CircuitOpen, litview_breaker

        async def _do() -> httpx.Response:
            try:
                return await self._http.get(path, params=params)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Same host as this project listens on :7070. A refused local
                # connection should not take the cards down while the public
                # site is still up.
                if await self._failover_to_public():
                    return await self._http.get(path, params=params)
                raise

        try:
            resp = await litview_breaker.call(_do)
        except CircuitOpen:
            raise httpx.ConnectError(f"litview circuit open ({path})")

        body: Any = None
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code >= 400:
            # Structured errors (404 not_found, 400 invalid_request) carry a JSON body.
            self._raise_structured(body, series=series, index=index)
            resp.raise_for_status()
        # Some structured errors arrive with 200 + {"error": ...}; honour them too.
        if isinstance(body, dict) and "error" in body and len(body) == 1:
            self._raise_structured(body, series=series, index=index)
        return body

    async def _cached_json(self, cache_key: str, ttl: int, path: str,
                           params: Optional[Dict[str, Any]] = None,
                           series: str = "", index: str = "") -> Any:
        # Values are wrapped so a cached `null` (not-yet-computed series) is a
        # hit too and does not hammer litview.
        cached = await self._cache_get(cache_key)
        if isinstance(cached, dict) and "v" in cached:
            return cached["v"]
        data = await self._get_json(path, params=params, series=series, index=index)
        await self._cache_set(cache_key, {"v": data}, ttl)
        return data

    # -- public API ----------------------------------------------------------

    async def get_sync_status(self) -> SyncStatus:
        data = await self._cached_json("sync", TTL_SYNC, "/api/server/sync")
        if not isinstance(data, dict):
            return SyncStatus()
        return SyncStatus(
            indexed_height=data.get("indexed_height"),
            computed_height=data.get("computed_height"),
            tip_height=data.get("tip_height"),
            blocks_behind=data.get("blocks_behind"),
            last_indexed_at=data.get("last_indexed_at"),
        )

    async def get_series_info(self, series: str) -> SeriesInfo:
        data = await self._cached_json(f"info:{series}", TTL_META, f"/api/series/{series}", series=series)
        if not isinstance(data, dict):
            raise LitviewSeriesNotFound(series)
        return SeriesInfo(series=series, indexes=list(data.get("indexes") or []), type=str(data.get("type") or ""))

    async def search(self, q: str, limit: int = 10) -> List[str]:
        q = (q or "").strip()
        if not q:
            return []
        data = await self._cached_json(
            f"search:{limit}:{q.lower()}", TTL_META, "/api/series/search", params={"q": q, "limit": limit}
        )
        return [str(s) for s in data] if isinstance(data, list) else []

    async def get_spot_price(self) -> Optional[Dict[str, Any]]:
        """
        Current LTC price from `/api/v1/prices`.

        On the co-hosted instance this is USD and a unix timestamp, current to
        the minute. Other fiat keys are included when the payload has them.
        Returns None when USD is missing — never a zero.
        """
        data = await self._cached_json("spot:v1:prices", TTL_LATEST, "/api/v1/prices")
        if not isinstance(data, dict):
            return None
        usd = _coerce_float(data.get("USD"))
        if usd is None or usd <= 0:
            return None
        out: Dict[str, Any] = {"USD": usd}
        try:
            out["time"] = int(data.get("time") or 0)
        except (TypeError, ValueError):
            out["time"] = 0
        for code in ("EUR", "GBP", "AUD", "JPY"):
            val = _coerce_float(data.get(code))
            if val is not None and val > 0:
                out[code] = val
        return out

    async def get_latest(self, series: str, index: str) -> Optional[float]:
        """Most recent value, or None when litview has not computed it."""
        data = await self._cached_json(
            f"latest:{series}:{index}", TTL_LATEST, f"/api/series/{series}/{index}/latest",
            series=series, index=index,
        )
        return _coerce_float(data)

    async def get_range(self, series: str, index: str, points: int = 30) -> SeriesRange:
        """
        Last `points` buckets with aligned timestamps (one bulk call:
        `timestamp,<series>`). `points` is clamped to [2, 2000].
        """
        n = max(2, min(int(points), 2000))
        data = await self._cached_json(
            f"range:{series}:{index}:{n}", range_ttl(index), "/api/series/bulk",
            params={"series": f"timestamp,{series}", "index": index, "start": -n},
            series=series, index=index,
        )
        if not isinstance(data, list) or len(data) < 2:
            raise LitviewError(f"unexpected bulk response for {series}/{index}")
        ts_block, val_block = data[0], data[1]
        ts = ts_block.get("data") if isinstance(ts_block, dict) else None
        vals = val_block.get("data") if isinstance(val_block, dict) else None
        ts = ts if isinstance(ts, list) else []
        vals = vals if isinstance(vals, list) else []
        length = max(len(ts), len(vals))
        pts: List[SeriesPoint] = []
        for i in range(length):
            t = ts[i] if i < len(ts) else None
            v = vals[i] if i < len(vals) else None
            t_int: Optional[int]
            try:
                t_int = int(t) if t is not None else None
            except (TypeError, ValueError):
                t_int = None
            pts.append(SeriesPoint(t=t_int, v=_coerce_float(v)))
        return SeriesRange(
            series=series,
            index=index,
            points=pts,
            stamp=val_block.get("stamp") if isinstance(val_block, dict) else None,
            version=val_block.get("version") if isinstance(val_block, dict) else None,
        )

    async def get_metric_snapshot(
        self,
        series: str,
        index: str = "day1",
        points: int = 30,
        change_windows: Tuple[int, ...] = (7, 30),
    ) -> MetricSnapshot:
        """
        Latest value + sparkline range + % changes, or `MetricNotComputed`.

        `latest` and the range are fetched concurrently. The value is the
        `/latest` number when present, else the last non-null point in range.
        """
        span = max(points, (max(change_windows) + 1) if change_windows else 0)
        latest_res, range_res = await asyncio.gather(
            self.get_latest(series, index),
            self.get_range(series, index, span),
            return_exceptions=True,
        )
        if isinstance(range_res, BaseException):
            raise range_res
        rng: SeriesRange = range_res
        latest: Optional[float] = None if isinstance(latest_res, BaseException) else latest_res

        last_pt = rng.last_non_null
        if latest is None and last_pt is None:
            # Nothing computed: explain how far litview has got.
            sync = SyncStatus()
            try:
                sync = await self.get_sync_status()
            except Exception as e:  # noqa: BLE001
                logger.debug("litview sync status unavailable: %s", e)
            raise MetricNotComputed(
                series, index,
                computed_height=sync.computed_height,
                computed_at=await self._height_to_date(sync.computed_height),
                tip_height=sync.tip_height,
            )

        value: float = latest if latest is not None else float(last_pt.v)  # type: ignore[union-attr, arg-type]
        as_of = (rng.points[-1].t if rng.points and latest is not None else None) or (last_pt.t if last_pt else None)

        # % changes vs N points back, measured from the last non-null point.
        vals = [p.v for p in rng.points]
        last_idx = max((i for i, v in enumerate(vals) if v is not None), default=None)
        changes: Dict[int, Optional[float]] = {}
        for w in change_windows:
            prev = None
            if last_idx is not None and last_idx - w >= 0:
                prev = vals[last_idx - w]
            changes[w] = pct_change(value, prev)

        tail = rng.points[-points:] if points and len(rng.points) > points else rng.points
        return MetricSnapshot(
            series=series, index=index, value=float(value), as_of=as_of, points=tail,
            changes_pct=changes, stamp=rng.stamp, endpoint=f"/api/series/{series}/{index}",
        )

    async def _height_to_date(self, height: Optional[int]) -> Optional[str]:
        """Best-effort ISO date for a block height via the explorer-compatible API."""
        if not height:
            return None
        try:
            cached = await self._cache_get(f"height_date:{height}")
            if isinstance(cached, str) and cached:
                return cached
            h = await self._get_json(f"/api/block-height/{height}")
            block_hash = h if isinstance(h, str) else None
            if not block_hash:
                return None
            block = await self._get_json(f"/api/block/{block_hash}")
            ts = block.get("timestamp") if isinstance(block, dict) else None
            if not ts:
                return None
            iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
            await self._cache_set(f"height_date:{height}", iso, TTL_META)
            return iso
        except Exception as e:  # noqa: BLE001
            logger.debug("litview height->date failed for %s: %s", height, e)
            return None


# ---------------------------------------------------------------------------
# Formatting helpers (shared by the graph node narration and tests)
# ---------------------------------------------------------------------------


def format_metric_value(value: float, unit: str) -> str:
    """Human formatting by unit: usd | ltc | percent | ratio | count | raw."""
    if unit == "usd":
        if abs(value) >= 1e9:
            return f"${value / 1e9:,.2f}B"
        if abs(value) >= 1e6:
            return f"${value / 1e6:,.2f}M"
        return f"${value:,.2f}"
    if unit == "ltc":
        if abs(value) >= 1e6:
            return f"{value / 1e6:,.2f}M LTC"
        return f"{value:,.2f} LTC"
    if unit == "percent":
        return f"{value:.2f}%"
    if unit == "ratio":
        return f"{value:.3f}"
    if unit == "count":
        if abs(value) >= 1e6:
            return f"{value / 1e6:,.2f}M"
        return f"{value:,.0f}"
    # raw
    if abs(value) >= 1e12:
        return f"{value:,.3e}"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.4g}"


def format_pct_change(pct: Optional[float]) -> str:
    if pct is None:
        return "n/a"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"
