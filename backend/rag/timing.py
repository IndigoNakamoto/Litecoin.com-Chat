"""Request-scoped chat hop timings (ms from generate_stream start)."""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Optional

chat_request_t0: ContextVar[Optional[float]] = ContextVar("chat_request_t0", default=None)


def mark_request_start() -> None:
    chat_request_t0.set(time.time())


def ms_since_t0() -> Optional[float]:
    t0 = chat_request_t0.get()
    if t0 is None:
        return None
    return (time.time() - t0) * 1000.0
