"""
Circuit breaker + bounded retry for Gemini (generation and Google Search grounding).

The LLM is the one dependency without a breaker today. When Gemini is
degraded we would rather tell the user plainly than retry forever or hand them
a half-streamed answer. Rules:

- `gemini_breaker` opens after `GEMINI_BREAKER_FAIL_THRESHOLD` consecutive
  failures and half-opens after `GEMINI_BREAKER_RESET_SECONDS`.
- `ainvoke_with_breaker` retries up to `GEMINI_MAX_ATTEMPTS` with exponential
  backoff (0.5s, 1s, 2s ...).
- `astream_with_breaker` retries only when the failure happens *before the
  first token*; once content has been emitted we surface the error, because a
  silent restart would duplicate text in the stream.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional

from backend.services.circuit_breaker import CircuitBreaker, CircuitOpen

logger = logging.getLogger(__name__)

GEMINI_MAX_ATTEMPTS = max(1, int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")))
GEMINI_RETRY_BASE_SECONDS = float(os.getenv("GEMINI_RETRY_BASE_SECONDS", "0.5"))
GEMINI_RETRY_MAX_SECONDS = float(os.getenv("GEMINI_RETRY_MAX_SECONDS", "4.0"))

gemini_breaker = CircuitBreaker(
    "gemini",
    fail_threshold=int(os.getenv("GEMINI_BREAKER_FAIL_THRESHOLD", "5")),
    reset_seconds=float(os.getenv("GEMINI_BREAKER_RESET_SECONDS", "60")),
)

LLM_UNAVAILABLE_MESSAGE = (
    "The answer service is temporarily unavailable, so I can't generate a response "
    "right now. I won't guess. Please try again in a minute."
)


class LLMUnavailable(RuntimeError):
    """Raised when Gemini is down (breaker open or retries exhausted)."""


def _record_tool_error(tool: str = "gemini") -> None:
    try:
        from backend.monitoring.metrics import tool_error_total

        tool_error_total.labels(tool=tool).inc()
    except Exception:
        pass


def _is_retryable(exc: BaseException) -> bool:
    """Heuristic: transient transport / quota / 5xx errors are retryable; bad input is not."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    non_retryable_markers = ("invalid argument", "permission denied", "unauthenticated", "api key")
    if any(m in text for m in non_retryable_markers):
        return False
    retryable_markers = (
        "timeout", "timed out", "temporarily", "unavailable", "deadline",
        "resource exhausted", "429", "500", "502", "503", "504",
        "connection", "reset by peer", "internal error", "overloaded",
    )
    return any(m in text for m in retryable_markers) or any(
        m in name for m in ("timeout", "connection", "serviceunavailable", "resourceexhausted", "internalservererror")
    )


def _backoff(attempt: int) -> float:
    return min(GEMINI_RETRY_BASE_SECONDS * (2 ** attempt), GEMINI_RETRY_MAX_SECONDS)


async def ainvoke_with_breaker(
    chain: Any,
    inputs: Dict[str, Any],
    *,
    max_attempts: Optional[int] = None,
    breaker: CircuitBreaker = gemini_breaker,
) -> Any:
    """`chain.ainvoke(inputs)` behind the Gemini breaker with bounded retry."""
    attempts = max_attempts or GEMINI_MAX_ATTEMPTS
    last_exc: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            return await breaker.call(lambda: chain.ainvoke(inputs))
        except CircuitOpen as e:
            _record_tool_error()
            raise LLMUnavailable(str(e)) from e
        except Exception as e:  # noqa: BLE001 - we classify below
            last_exc = e
            _record_tool_error()
            if attempt + 1 >= attempts or not _is_retryable(e):
                break
            delay = _backoff(attempt)
            logger.warning(
                "Gemini invoke failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1, attempts, e, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    if _is_retryable(last_exc):
        raise LLMUnavailable(str(last_exc)) from last_exc
    raise last_exc


async def astream_with_breaker(
    chain: Any,
    inputs: Dict[str, Any],
    *,
    max_attempts: Optional[int] = None,
    breaker: CircuitBreaker = gemini_breaker,
) -> AsyncIterator[Any]:
    """`chain.astream(inputs)` behind the Gemini breaker.

    Retries (with backoff) only if the stream fails before yielding anything.
    """
    if breaker.state == "open":
        _record_tool_error()
        raise LLMUnavailable(f"{breaker.name} circuit open")

    attempts = max_attempts or GEMINI_MAX_ATTEMPTS
    last_exc: Optional[BaseException] = None
    for attempt in range(attempts):
        emitted = False
        try:
            async for chunk in chain.astream(inputs):
                emitted = True
                yield chunk
            breaker.failures = 0
            breaker.opened_at = None
            return
        except Exception as e:  # noqa: BLE001
            last_exc = e
            _record_tool_error()
            breaker.failures += 1
            if breaker.failures >= breaker.fail_threshold:
                import time as _time

                breaker.opened_at = _time.monotonic()
                logger.warning("%s circuit opened after %s failures", breaker.name, breaker.failures)
            if emitted or attempt + 1 >= attempts or not _is_retryable(e):
                break
            delay = _backoff(attempt)
            logger.warning(
                "Gemini stream failed before first token (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1, attempts, e, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    if _is_retryable(last_exc):
        raise LLMUnavailable(str(last_exc)) from last_exc
    raise last_exc


async def call_with_payload_breaker(factory: Callable[[], Awaitable[Any]]) -> Any:
    """Run a Payload CMS HTTP call behind the shared `payload_breaker`."""
    from backend.services.circuit_breaker import payload_breaker

    try:
        return await payload_breaker.call(factory)
    except Exception:
        _record_tool_error("payload")
        raise
