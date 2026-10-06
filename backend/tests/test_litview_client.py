"""
litview.space Series API client.

Fixtures below are recorded from live probes of https://litview.space on
2026-10-04/05 (LRK v0.11.2): shapes for /latest, /bulk, /series/{s},
/server/sync and the structured error bodies.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.services import litview_client as lv
from backend.services.litview_client import (
    LitviewClient,
    LitviewSeriesNotFound,
    LitviewUnsupportedIndex,
    MetricNotComputed,
    format_metric_value,
    format_pct_change,
    pct_change,
)

# --- recorded fixtures -----------------------------------------------------

SYNC = {"indexed_height": 3189496, "computed_height": 2520000, "tip_height": 3189505,
        "blocks_behind": 9, "last_indexed_at": "2026-09-12T17:56:24Z", "last_indexed_at_unix": 1789235784}

INFO_MVRV = {"indexes": ["minute10", "minute30", "hour1", "hour4", "hour12", "day1", "day3", "week1",
                         "month1", "month3", "month6", "year1", "year10", "halving", "epoch", "height"],
             "type": "StoredF32"}

BULK_PRICE_CLOSE = [
    {"version": 23, "index": "day1", "type": "Timestamp", "start": 5749, "end": 5757,
     "stamp": "2026-10-05T19:23:02Z",
     "data": [1790553600, 1790640000, 1790726400, 1790812800, 1790899200, 1790985600, 1791072000, 1791158400]},
    {"version": 91, "index": "day1", "type": "Dollars", "start": 5749, "end": 5757,
     "stamp": "2026-10-05T19:23:03Z",
     "data": [69.19, 66.82, 67.21, 69.87, 70.28, 70.7, 70.19, 71.67]},
]

BULK_MVRV_NULL = [
    {"version": 23, "index": "day1", "type": "Timestamp", "start": 5749, "end": 5757,
     "stamp": "2026-10-04T16:24:20Z",
     "data": [1790553600, 1790640000, 1790726400, 1790812800, 1790899200, 1790985600, 1791072000, 1791158400]},
    {"version": 335, "index": "day1", "type": "StoredF32", "start": 5749, "end": 5757,
     "stamp": "2026-10-04T16:24:20Z", "data": [None] * 8},
]

ERR_NOT_FOUND = {"error": {"type": "not_found", "code": "series_not_found",
                           "message": "'nope_series' not found", "doc_url": "/api"}}
ERR_UNSUPPORTED = {"error": {"type": "invalid_request", "code": "series_unsupported_index",
                             "message": "'tx_count' doesn't support the requested index. Try: /api/series/tx_count/height",
                             "doc_url": "/api"}}


# --- fake transport ----------------------------------------------------------

class _Resp:
    def __init__(self, status: int, body: Any):
        self.status_code = status
        self._body = body
        self.request = httpx.Request("GET", "https://litview.space/x")

    def json(self):
        if self._body is _RAW_TEXT:
            raise ValueError("not json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=self.request, response=self)  # type: ignore[arg-type]


_RAW_TEXT = object()


def _route(url: str, params: Optional[Dict[str, Any]]) -> _Resp:
    p = params or {}
    if url == "/api/server/sync":
        return _Resp(200, SYNC)
    if url == "/api/series/mvrv":
        return _Resp(200, INFO_MVRV)
    if url == "/api/series/price_close/day1/latest":
        return _Resp(200, 71.67)
    if url == "/api/series/mvrv/day1/latest":
        return _Resp(200, None)
    if url == "/api/series/nope_series/day1/latest":
        return _Resp(404, ERR_NOT_FOUND)
    if url == "/api/series/tx_count/day1/latest":
        return _Resp(400, ERR_UNSUPPORTED)
    if url == "/api/series/bulk":
        if p.get("series") == "timestamp,price_close":
            return _Resp(200, BULK_PRICE_CLOSE)
        if p.get("series") == "timestamp,mvrv":
            return _Resp(200, BULK_MVRV_NULL)
    if url == "/api/series/search":
        return _Resp(200, ["mvrv", "lth_mvrv", "sth_mvrv"])
    if url == "/api/v1/prices":
        return _Resp(200, {"time": 1791302952, "USD": 69.96})
    if url == "/api/block-height/2520000":
        return _Resp(200, "54cd0ef48a977c5bb9c845e0c67a4e9d17a5894b084aea4bf7e594122f5c0dc1")
    if url.startswith("/api/block/54cd0ef4"):
        return _Resp(200, {"height": 2520000, "timestamp": 1690988793})
    return _Resp(404, {"error": {"type": "not_found", "code": "no_data", "message": "No data available"}})


class _FakeRedis:
    def __init__(self):
        self.store: Dict[str, Tuple[str, int]] = {}

    async def get(self, key):
        v = self.store.get(key)
        return v[0] if v else None

    async def set(self, key, value, ex=None):
        self.store[key] = (value, ex or 0)


@pytest.fixture
def client(monkeypatch):
    # Fresh breaker per test so an open circuit does not leak.
    from backend.services import circuit_breaker as cb

    monkeypatch.setattr(cb, "litview_breaker", cb.CircuitBreaker("litview-test"))
    c = LitviewClient(redis_client=_FakeRedis(), base_url="https://litview.space")
    c._http = MagicMock()
    c._http.get = AsyncMock(side_effect=lambda url, params=None: _route(url, params))
    c._http.aclose = AsyncMock()
    return c


# --- tests -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_status_and_series_info(client):
    s = await client.get_sync_status()
    assert s.computed_height == 2520000 and s.tip_height == 3189505
    info = await client.get_series_info("mvrv")
    assert "day1" in info.indexes and info.type == "StoredF32"


@pytest.mark.asyncio
async def test_latest_value_and_null(client):
    assert await client.get_latest("price_close", "day1") == 71.67
    assert await client.get_latest("mvrv", "day1") is None


@pytest.mark.asyncio
async def test_null_latest_is_cached_and_does_not_refetch(client):
    await client.get_latest("mvrv", "day1")
    await client.get_latest("mvrv", "day1")
    calls = [c.args[0] for c in client._http.get.await_args_list]
    assert calls.count("/api/series/mvrv/day1/latest") == 1
    key = lv.CACHE_KEY_PREFIX + "latest:mvrv:day1"
    assert json.loads(client._redis.store[key][0]) == {"v": None}
    assert client._redis.store[key][1] == lv.TTL_LATEST


@pytest.mark.asyncio
async def test_range_aligns_timestamps_with_values(client):
    rng = await client.get_range("price_close", "day1", points=8)
    assert len(rng.points) == 8
    assert rng.points[-1].t == 1791158400 and rng.points[-1].v == 71.67
    assert rng.last_non_null.v == 71.67
    # bulk request shape: `timestamp,<series>`, negative start counts from the end
    _, kwargs = client._http.get.await_args
    assert kwargs["params"] == {"series": "timestamp,price_close", "index": "day1", "start": -8}


@pytest.mark.asyncio
async def test_structured_errors_map_to_exceptions(client):
    with pytest.raises(LitviewSeriesNotFound):
        await client.get_latest("nope_series", "day1")
    with pytest.raises(LitviewUnsupportedIndex):
        await client.get_latest("tx_count", "day1")


@pytest.mark.asyncio
async def test_metric_snapshot_value_changes_and_tail(client):
    snap = await client.get_metric_snapshot("price_close", "day1", points=5, change_windows=(3, 7))
    assert snap.value == 71.67
    assert snap.as_of == 1791158400
    assert len(snap.points) == 5  # sparkline tail trimmed to `points`
    assert snap.changes_pct[3] == pytest.approx(pct_change(71.67, 70.28))
    assert snap.changes_pct[7] == pytest.approx(pct_change(71.67, 69.19))
    assert snap.endpoint == "/api/series/price_close/day1"


@pytest.mark.asyncio
async def test_metric_snapshot_not_computed_carries_sync_context(client):
    with pytest.raises(MetricNotComputed) as ei:
        await client.get_metric_snapshot("mvrv", "day1", points=5)
    err = ei.value
    assert err.series == "mvrv"
    assert err.computed_height == 2520000
    assert err.tip_height == 3189505
    assert err.computed_at == "2023-08-02"  # block 2,520,000 timestamp -> date


@pytest.mark.asyncio
async def test_breaker_open_surfaces_as_connect_error(client):
    from backend.services import circuit_breaker as cb

    cb.litview_breaker.opened_at = 1e18  # force open
    with pytest.raises(httpx.ConnectError):
        await client.get_sync_status()


@pytest.mark.asyncio
async def test_spot_price_is_usd_and_drops_missing_fiat(client):
    spot = await client.get_spot_price()
    assert spot == {"USD": 69.96, "time": 1791302952}


@pytest.mark.asyncio
async def test_connect_error_fails_over_to_public_site(monkeypatch):
    from backend.services import circuit_breaker as cb

    monkeypatch.setattr(cb, "litview_breaker", cb.CircuitBreaker("litview-failover"))

    class _Http:
        def __init__(self, base_url, **_kwargs):
            self.base_url = str(base_url)

        async def get(self, url, params=None):
            if "7070" in self.base_url:
                raise httpx.ConnectError("connection refused")
            assert url == "/api/v1/prices"
            return _Resp(200, {"time": 1791302952, "USD": 69.96})

        async def aclose(self):
            return None

    monkeypatch.setattr(lv.httpx, "AsyncClient", _Http)
    client = LitviewClient(base_url="http://host.docker.internal:7070")
    spot = await client.get_spot_price()
    assert spot["USD"] == 69.96
    assert client.base_url == lv.LITVIEW_PUBLIC_URL


@pytest.mark.asyncio
async def test_search_returns_names(client):
    assert await client.search("mvrv", limit=3) == ["mvrv", "lth_mvrv", "sth_mvrv"]
    assert await client.search("   ") == []


def test_formatting_helpers():
    assert format_metric_value(71.67, "usd") == "$71.67"
    assert format_metric_value(2_500_000_000, "usd") == "$2.50B"
    assert format_metric_value(76_000_000, "ltc") == "76.00M LTC"
    assert format_metric_value(1.2345, "ratio") == "1.234"
    assert format_metric_value(3.14159, "percent") == "3.14%"
    assert format_metric_value(4243, "count") == "4,243"
    assert format_pct_change(None) == "n/a"
    assert format_pct_change(2.04) == "+2.0%"
    assert format_pct_change(-0.5) == "-0.5%"
    assert pct_change(110, 100) == pytest.approx(10.0)
    assert pct_change(1, 0) is None
