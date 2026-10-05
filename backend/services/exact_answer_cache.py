"""
Exact-text answer cache (Redis).

A cheap first tier in front of the semantic (vector) cache for *empty-history*
questions: the key is the normalised question text, so a repeat of a question
anyone has asked before is served without the Infinity embedding call
(60-600 ms) the vector cache needs before it can even look anything up.

Entries carry the cited `payload_ids`, so the CMS webhook can drop them when an
article changes (`sync/payload.invalidate_cached_answers_for`), and the
`is_grounded` flag so a web-supplemented answer is still labelled as such on a
hit. Low-confidence / web-only / abstained answers are never written here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KEY_PREFIX = "cache:exact:"
_TRAILING_PUNCT = re.compile(r"[\s?!.。！？]+$")
_WS = re.compile(r"\s+")


def normalize_question(text: str) -> str:
    """Lowercase, collapse whitespace, drop trailing punctuation."""
    s = (text or "").strip().lower()
    s = _WS.sub(" ", s)
    s = _TRAILING_PUNCT.sub("", s)
    return s


def _payload_ids(sources: List[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for src in sources or []:
        meta = src.get("metadata") if isinstance(src, dict) else None
        if not isinstance(meta, dict):
            continue
        pid = meta.get("payload_id")
        if pid and str(pid) not in ids:
            ids.append(str(pid))
    return ids


@dataclass
class ExactCacheEntry:
    query: str
    answer: str
    sources: List[Dict[str, Any]]
    is_grounded: bool = False
    cached_at: float = 0.0


class ExactAnswerCache:
    """Redis hash per normalised question; TTL defaults to the semantic cache's."""

    def __init__(self, ttl_seconds: Optional[int] = None):
        if ttl_seconds is None:
            ttl_seconds = int(
                os.getenv("EXACT_CACHE_TTL_SECONDS", os.getenv("REDIS_CACHE_TTL_SECONDS", str(7 * 24 * 3600)))
            )
        self.ttl_seconds = max(0, int(ttl_seconds))
        self._client = None

    # -- infra -------------------------------------------------------------

    async def _get_client(self):
        if self._client is None:
            from backend.redis_client import get_redis_client

            self._client = await get_redis_client()
        return self._client

    @staticmethod
    def key_for(question: str) -> str:
        return KEY_PREFIX + hashlib.sha1(normalize_question(question).encode("utf-8")).hexdigest()

    # -- api ---------------------------------------------------------------

    async def get(self, question: str) -> Optional[ExactCacheEntry]:
        if not normalize_question(question):
            return None
        try:
            client = await self._get_client()
            raw = await client.hgetall(self.key_for(question))
        except Exception as e:
            logger.warning("Exact answer cache lookup failed: %s", e)
            return None
        if not raw:
            return None

        def _s(k: str) -> str:
            v = raw.get(k) if k in raw else raw.get(k.encode("utf-8"))
            if v is None:
                return ""
            return v.decode("utf-8", errors="ignore") if isinstance(v, bytes) else str(v)

        answer = _s("answer")
        if not answer:
            return None
        try:
            sources = json.loads(_s("sources") or "[]")
        except Exception:
            sources = []
        try:
            cached_at = float(_s("cached_at") or 0.0)
        except ValueError:
            cached_at = 0.0
        return ExactCacheEntry(
            query=_s("query"),
            answer=answer,
            sources=sources if isinstance(sources, list) else [],
            is_grounded=_s("is_grounded") == "1",
            cached_at=cached_at,
        )

    async def set(
        self,
        question: str,
        answer: str,
        sources: List[Dict[str, Any]],
        is_grounded: bool = False,
    ) -> bool:
        if not normalize_question(question) or not (answer or "").strip():
            return False
        try:
            client = await self._get_client()
            key = self.key_for(question)
            await client.hset(
                key,
                mapping={
                    "query": question,
                    "answer": answer,
                    "sources": json.dumps(sources or [], default=str),
                    "is_grounded": "1" if is_grounded else "0",
                    "payload_ids": " ".join(_payload_ids(sources or [])),
                    "cached_at": str(time.time()),
                },
            )
            if self.ttl_seconds > 0:
                await client.expire(key, self.ttl_seconds)
            return True
        except Exception as e:
            logger.warning("Exact answer cache store failed: %s", e)
            return False

    async def invalidate_by_payload_id(self, payload_id: str) -> int:
        """Delete every entry that cited the given Payload CMS document."""
        if not payload_id:
            return 0
        target = str(payload_id)
        removed = 0
        try:
            client = await self._get_client()
            async for key in client.scan_iter(match=f"{KEY_PREFIX}*"):
                raw = await client.hget(key, "payload_ids")
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                if target in raw.split():
                    await client.delete(key)
                    removed += 1
            if removed:
                logger.info("Invalidated %d exact-cache entr%s citing payload_id=%s",
                            removed, "y" if removed == 1 else "ies", target)
        except Exception as e:
            logger.warning("Exact answer cache invalidate failed for payload_id=%s: %s", target, e)
        return removed

    async def clear(self) -> int:
        removed = 0
        try:
            client = await self._get_client()
            keys = [k async for k in client.scan_iter(match=f"{KEY_PREFIX}*")]
            if keys:
                await client.delete(*keys)
                removed = len(keys)
        except Exception as e:
            logger.warning("Exact answer cache clear failed: %s", e)
        return removed

    async def stats(self) -> Dict[str, Any]:
        try:
            client = await self._get_client()
            n = 0
            async for _ in client.scan_iter(match=f"{KEY_PREFIX}*"):
                n += 1
            return {"entries": n, "ttl_seconds": self.ttl_seconds, "key_prefix": KEY_PREFIX}
        except Exception as e:
            return {"entries": 0, "ttl_seconds": self.ttl_seconds, "error": str(e)}
