"""
Known published article ids, cached briefly.

Source chips are built from whatever metadata a cache entry or chunk carries.
Caches seeded from another environment, or chunks for an article that was
since deleted, would otherwise produce chips that 404. Filtering against the
set of ids actually in the vector store keeps the trust surface honest.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional, Set

logger = logging.getLogger(__name__)

_TTL_SECONDS = int(os.getenv("KNOWN_ARTICLE_IDS_TTL_SECONDS", "300"))
_cache: Set[str] = set()
_cached_at: float = 0.0


async def get_known_payload_ids(force: bool = False) -> Optional[Set[str]]:
    """Distinct published `payload_id`s in the vector store. None if Mongo is unavailable."""
    global _cache, _cached_at
    now = time.monotonic()
    if not force and _cache and now - _cached_at < _TTL_SECONDS:
        return _cache
    try:
        from backend.dependencies import MONGO_DATABASE_NAME, get_mongo_client

        client = await get_mongo_client()
        if client is None:
            return _cache or None
        coll = client[MONGO_DATABASE_NAME][os.getenv("MONGO_COLLECTION_NAME", "litecoin_docs")]
        ids = await coll.distinct("metadata.payload_id", {"metadata.status": "published"})
        _cache = {str(i) for i in ids if i}
        _cached_at = now
        return _cache
    except Exception as e:  # noqa: BLE001
        logger.debug("known payload ids refresh failed: %s", e)
        return _cache or None


def invalidate_known_payload_ids() -> None:
    """Call after ingest/delete so the next request re-reads the set."""
    global _cached_at
    _cached_at = 0.0
