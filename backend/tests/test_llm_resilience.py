"""Gemini circuit breaker + bounded retry, and blockchain card provenance."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.services import llm_resilience as lr
from backend.services.circuit_breaker import CircuitBreaker


class _FlakyChain:
    """ainvoke/astream that fail `fail_times` times then succeed."""

    def __init__(self, fail_times: int, exc: Exception = None, fail_mid_stream: bool = False):
        self.fail_times = fail_times
        self.exc = exc or RuntimeError("503 Service Unavailable")
        self.calls = 0
        self.fail_mid_stream = fail_mid_stream

    async def ainvoke(self, inputs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return {"content": "ok"}

    async def astream(self, inputs):
        self.calls += 1
        if self.calls <= self.fail_times:
            if self.fail_mid_stream:
                yield "partial"
            raise self.exc
        yield "a"
        yield "b"


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    monkeypatch.setattr(lr, "GEMINI_RETRY_BASE_SECONDS", 0.0)
    monkeypatch.setattr(lr, "GEMINI_RETRY_MAX_SECONDS", 0.0)


@pytest.mark.asyncio
async def test_ainvoke_retries_transient_then_succeeds():
    breaker = CircuitBreaker("t", fail_threshold=10)
    chain = _FlakyChain(fail_times=2)
    out = await lr.ainvoke_with_breaker(chain, {}, max_attempts=3, breaker=breaker)
    assert out == {"content": "ok"}
    assert chain.calls == 3
    assert breaker.failures == 0


@pytest.mark.asyncio
async def test_ainvoke_exhausted_raises_llm_unavailable():
    breaker = CircuitBreaker("t", fail_threshold=10)
    chain = _FlakyChain(fail_times=5)
    with pytest.raises(lr.LLMUnavailable):
        await lr.ainvoke_with_breaker(chain, {}, max_attempts=2, breaker=breaker)
    assert chain.calls == 2


@pytest.mark.asyncio
async def test_ainvoke_non_retryable_error_is_not_retried():
    breaker = CircuitBreaker("t", fail_threshold=10)
    chain = _FlakyChain(fail_times=5, exc=ValueError("Invalid argument: bad prompt"))
    with pytest.raises(ValueError):
        await lr.ainvoke_with_breaker(chain, {}, max_attempts=3, breaker=breaker)
    assert chain.calls == 1


@pytest.mark.asyncio
async def test_ainvoke_open_breaker_short_circuits():
    breaker = CircuitBreaker("t", fail_threshold=1, reset_seconds=999)
    with pytest.raises(Exception):
        await breaker.call(lambda: _FlakyChain(1).ainvoke({}))
    assert breaker.state == "open"

    chain = _FlakyChain(fail_times=0)
    with pytest.raises(lr.LLMUnavailable):
        await lr.ainvoke_with_breaker(chain, {}, breaker=breaker)
    assert chain.calls == 0


@pytest.mark.asyncio
async def test_astream_retries_before_first_token():
    breaker = CircuitBreaker("t", fail_threshold=10)
    chain = _FlakyChain(fail_times=1)
    chunks: List[str] = []
    async for c in lr.astream_with_breaker(chain, {}, max_attempts=3, breaker=breaker):
        chunks.append(c)
    assert chunks == ["a", "b"]
    assert chain.calls == 2
    assert breaker.failures == 0


@pytest.mark.asyncio
async def test_astream_does_not_retry_after_first_token():
    breaker = CircuitBreaker("t", fail_threshold=10)
    chain = _FlakyChain(fail_times=1, fail_mid_stream=True)
    chunks: List[str] = []
    with pytest.raises(lr.LLMUnavailable):
        async for c in lr.astream_with_breaker(chain, {}, max_attempts=3, breaker=breaker):
            chunks.append(c)
    assert chunks == ["partial"]
    assert chain.calls == 1


@pytest.mark.asyncio
async def test_astream_opens_breaker_after_threshold():
    breaker = CircuitBreaker("t", fail_threshold=2, reset_seconds=999)
    chain = _FlakyChain(fail_times=10)
    with pytest.raises(lr.LLMUnavailable):
        async for _ in lr.astream_with_breaker(chain, {}, max_attempts=2, breaker=breaker):
            pass
    assert breaker.state == "open"

    with pytest.raises(lr.LLMUnavailable):
        async for _ in lr.astream_with_breaker(_FlakyChain(0), {}, breaker=breaker):
            pass


def test_is_retryable_classification():
    assert lr._is_retryable(RuntimeError("503 Service Unavailable"))
    assert lr._is_retryable(RuntimeError("Deadline exceeded"))
    assert lr._is_retryable(TimeoutError())
    assert not lr._is_retryable(RuntimeError("API key not valid"))
    assert not lr._is_retryable(ValueError("Invalid argument"))


def test_blockchain_provenance_stamp():
    from backend.rag_graph.nodes.blockchain_lookup import _stamp_provenance

    out = _stamp_provenance({"fastestFee": 2}, "fees")
    assert out["fastestFee"] == 2
    prov = out["_provenance"]
    assert prov["source"] == "Litecoin Space"
    assert prov["endpoint"] == "/api/v1/fees/recommended"
    assert prov["fetched_at"].endswith("+00:00")
    # non-dict payloads pass through untouched
    assert _stamp_provenance(None, "fees") is None
