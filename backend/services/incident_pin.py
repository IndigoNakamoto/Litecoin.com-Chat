"""
Incident override ("pin").

One Redis key, `admin:incident_pin`, holding a pinned answer that bypasses
retrieval until it is cleared or expires. Used for a delisting, a Core
release, or a scam wave: the difference between a knowledge bot and a
Foundation channel during a bad afternoon.

Semantics
---------
- `match_terms` empty  -> every non-blockchain, non-refused question gets the pin.
- `match_terms` set    -> the pin is served only when any term appears in the
                          (lower-cased) question; everything else flows normally.
- `expires_at`         -> ISO-8601; Redis TTL is also set so a forgotten pin dies.
- Pinned answers are never written to any cache, and cache hits are skipped
  while a pin matches (a fresh crisis answer must beat a stale cached one).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

INCIDENT_PIN_KEY = os.getenv("INCIDENT_PIN_REDIS_KEY", "admin:incident_pin")
MAX_PIN_TTL_HOURS = int(os.getenv("INCIDENT_PIN_MAX_HOURS", "168"))  # 7 days


class IncidentPin(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = Field(..., min_length=3, max_length=140)
    answer: str = Field(..., min_length=10, max_length=6000, description="Markdown shown to every matching reader.")
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional source chips [{title, url}] rendered under the pinned answer.",
    )
    match_terms: List[str] = Field(
        default_factory=list,
        description="Lower-cased substrings; empty means the pin applies to every question.",
    )
    expires_at: datetime = Field(..., description="When the pin stops being served.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = Field(None, max_length=80)

    @field_validator("match_terms")
    @classmethod
    def _norm_terms(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for t in v or []:
            t2 = (t or "").strip().lower()
            if t2 and t2 not in out and len(t2) >= 3:
                out.append(t2)
        return out[:30]

    @field_validator("expires_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.expires_at <= now

    def matches(self, query: str) -> bool:
        if self.is_expired():
            return False
        if not self.match_terms:
            return True
        q = (query or "").lower()
        return any(term in q for term in self.match_terms)


class IncidentPinCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=140)
    answer: str = Field(..., min_length=10, max_length=6000)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    match_terms: List[str] = Field(default_factory=list)
    ttl_hours: float = Field(24, gt=0, le=MAX_PIN_TTL_HOURS)
    created_by: Optional[str] = Field(None, max_length=80)


async def get_pin(redis_client: Any) -> Optional[IncidentPin]:
    if redis_client is None:
        return None
    try:
        raw = await redis_client.get(INCIDENT_PIN_KEY)
    except Exception as e:  # noqa: BLE001
        logger.debug("Incident pin read failed: %s", e)
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    try:
        pin = IncidentPin.model_validate(json.loads(raw))
    except Exception as e:  # noqa: BLE001
        logger.warning("Incident pin payload invalid, ignoring: %s", e)
        return None
    if pin.is_expired():
        return None
    return pin


async def set_pin(redis_client: Any, data: IncidentPinCreate) -> IncidentPin:
    pin = IncidentPin(
        title=data.title,
        answer=data.answer,
        sources=data.sources,
        match_terms=data.match_terms,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=data.ttl_hours),
        created_by=data.created_by,
    )
    ttl_seconds = max(60, int(data.ttl_hours * 3600))
    await redis_client.set(INCIDENT_PIN_KEY, pin.model_dump_json(), ex=ttl_seconds)
    logger.warning("Incident pin SET id=%s title=%r terms=%s expires=%s", pin.id, pin.title, pin.match_terms, pin.expires_at)
    return pin


async def clear_pin(redis_client: Any) -> bool:
    try:
        removed = await redis_client.delete(INCIDENT_PIN_KEY)
    except Exception as e:  # noqa: BLE001
        logger.warning("Incident pin clear failed: %s", e)
        return False
    if removed:
        logger.warning("Incident pin CLEARED")
    return bool(removed)
