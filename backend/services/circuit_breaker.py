"""Simple circuit breaker for optional dependencies (Space, Infinity, Payload)."""

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitOpen(RuntimeError):
    """Raised when the breaker is open and the call is short-circuited."""


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        fail_threshold: int = 3,
        reset_seconds: float = 30.0,
    ):
        self.name = name
        self.fail_threshold = fail_threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if (time.monotonic() - self.opened_at) >= self.reset_seconds:
            return "half_open"
        return "open"

    async def call(self, factory: Callable[[], Awaitable[T]]) -> T:
        if self.state == "open":
            raise CircuitOpen(f"{self.name} circuit open")
        try:
            result = await factory()
            self.failures = 0
            self.opened_at = None
            return result
        except CircuitOpen:
            raise
        except Exception:
            self.failures += 1
            if self.failures >= self.fail_threshold:
                self.opened_at = time.monotonic()
                logger.warning("%s circuit opened after %s failures", self.name, self.failures)
            raise


space_breaker = CircuitBreaker("litecoin_space")
infinity_breaker = CircuitBreaker("infinity")
payload_breaker = CircuitBreaker("payload")
