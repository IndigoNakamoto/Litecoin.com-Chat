"""
Public, read-only article endpoint for the in-chat article modal.

GET /api/v1/articles/{id}

Returns a published Payload article as markdown + provenance. The chat UI
calls this through its own origin (`/api/v1/*` is rewritten to the backend),
so a reader on litecoin.com/chat never has to leave the page to read a source.
Drafts and unknown ids are 404. Responses are cached in-process for a few
minutes and invalidated by the CMS webhook.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from backend.rate_limiter import RateLimitConfig, check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter()

ARTICLE_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=int(os.getenv("ARTICLE_READ_RATE_LIMIT_PER_MINUTE", "60")),
    requests_per_hour=int(os.getenv("ARTICLE_READ_RATE_LIMIT_PER_HOUR", "600")),
    identifier="article_read",
)

_ID_RE = re.compile(r"^[a-f0-9]{24}$", re.IGNORECASE)
_CACHE_TTL = int(os.getenv("ARTICLE_READ_CACHE_SECONDS", "300"))
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _payload_base() -> str:
    return (
        os.getenv("PAYLOAD_URL")
        or os.getenv("PAYLOAD_INTERNAL_URL")
        or os.getenv("PAYLOAD_PUBLIC_SERVER_URL")
        or "http://payload_cms:3000"
    ).rstrip("/")


def _localized(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        en = value.get("en")
        if isinstance(en, str):
            return en
        for v in value.values():
            if isinstance(v, str):
                return v
    return ""


def invalidate_article(article_id: Optional[str] = None) -> None:
    if article_id:
        _cache.pop(str(article_id), None)
    else:
        _cache.clear()


async def _fetch(article_id: str) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    hit = _cache.get(article_id)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    url = f"{_payload_base()}/api/articles/{article_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"depth": 0, "locale": "en"}, headers={"Accept": "application/json"})
    except Exception as e:  # noqa: BLE001
        logger.warning("article fetch failed for %s: %s", article_id, e)
        raise HTTPException(status_code=503, detail={"error": "CMS unavailable"})
    if resp.status_code in (403, 404):
        return None
    if resp.status_code != 200:
        logger.warning("article fetch %s -> %s", article_id, resp.status_code)
        raise HTTPException(status_code=502, detail={"error": "CMS error"})
    doc = resp.json()
    if not isinstance(doc, dict) or doc.get("status") != "published":
        return None
    markdown = doc.get("markdown") if isinstance(doc.get("markdown"), str) else ""
    if not markdown:
        return None
    out = {
        "id": str(doc.get("id") or article_id),
        "title": _localized(doc.get("title")) or "Untitled",
        "markdown": markdown,
        "source_url": doc.get("sourceUrl") if isinstance(doc.get("sourceUrl"), str) else None,
        "source_tier": doc.get("sourceTier") or "cms",
        "updated_at": doc.get("updatedAt"),
        "published_date": doc.get("publishedDate"),
        "last_reviewed_at": doc.get("lastReviewedAt"),
        "review_interval_days": doc.get("reviewIntervalDays"),
    }
    _cache[article_id] = (now, out)
    return out


@router.get("/articles/{article_id}")
async def read_article(article_id: str, request: Request, response: Response) -> Dict[str, Any]:
    if not _ID_RE.match(article_id or ""):
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    await check_rate_limit(request, ARTICLE_RATE_LIMIT)
    article = await _fetch(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "This article is not published or no longer exists."})
    response.headers["Cache-Control"] = f"public, max-age={_CACHE_TTL}"
    return article
