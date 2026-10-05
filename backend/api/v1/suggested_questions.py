"""
Public landing-page data for the chat UI.

GET /api/v1/suggested-questions[?category=<id>&locale=en]

One request replaces the three the browser used to make straight to Payload
(active questions, all questions, and - now - categories), goes through the
frontend's own `/api/v1/*` rewrite (no CORS to the CMS host), and annotates each
question with `cached` so the UI can mark questions that will answer instantly
from the suggested-question cache.

Shape:
  {
    "categories": [{id, name, description, icon, audienceLevel, order, parentId, questionCount}],
    "questions":  [{id, question, order, isActive, categoryId, cached}],
    "fallback":   false        # true when the CMS was unreachable and nothing could be served
  }

`questions` includes inactive ones (flagged) because "I'm Feeling Lit" draws
from the whole pool, exactly as the old direct-to-Payload code did.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from backend.rate_limiter import RateLimitConfig, check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter()

SUGGESTED_QUESTIONS_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=int(os.getenv("SUGGESTED_QUESTIONS_RATE_LIMIT_PER_MINUTE", "60")),
    requests_per_hour=int(os.getenv("SUGGESTED_QUESTIONS_RATE_LIMIT_PER_HOUR", "600")),
    identifier="suggested_questions",
)

# In-process TTL cache for the raw CMS payload (Payload has no webhook for this
# collection, so freshness is TTL-bound; editors see changes within a minute).
_CACHE_TTL = int(os.getenv("SUGGESTED_QUESTIONS_CACHE_SECONDS", "60"))
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

_ALLOWED_LOCALES = {"en", "es", "fr"}


def _payload_base() -> str:
    return (
        os.getenv("PAYLOAD_URL")
        or os.getenv("PAYLOAD_INTERNAL_URL")
        or os.getenv("PAYLOAD_PUBLIC_SERVER_URL")
        or "http://payload_cms:3000"
    ).rstrip("/")


def invalidate() -> None:
    _cache.clear()


def _relation_id(value: Any) -> Optional[str]:
    """Payload relationships arrive as an id string (depth=0) or an object (depth>0)."""
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        rid = value.get("id")
        return str(rid) if rid else None
    return None


def _localized(value: Any, locale: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in (locale, "en"):
            v = value.get(key)
            if isinstance(v, str) and v:
                return v
        for v in value.values():
            if isinstance(v, str) and v:
                return v
    return ""


async def _fetch_cms(locale: str) -> Dict[str, Any]:
    """Fetch categories + all questions from Payload (cached in-process)."""
    now = time.monotonic()
    hit = _cache.get(locale)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]

    base = _payload_base()
    params_q = {"sort": "order", "limit": "100", "depth": "0", "locale": locale}
    params_c = {"sort": "order", "limit": "100", "depth": "0", "locale": locale}
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"Accept": "application/json"}) as client:
            q_resp, c_resp = await _gather(
                client.get(f"{base}/api/suggested-questions", params=params_q),
                client.get(f"{base}/api/categories", params=params_c),
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("suggested-questions CMS fetch failed: %s", e)
        raise HTTPException(status_code=503, detail={"error": "cms_unavailable"})

    if isinstance(q_resp, Exception):
        logger.warning("suggested-questions CMS fetch failed: %s", q_resp)
        raise HTTPException(status_code=503, detail={"error": "cms_unavailable"})
    if q_resp.status_code != 200:
        logger.warning("suggested-questions fetch -> %s", q_resp.status_code)
        raise HTTPException(status_code=502, detail={"error": "cms_error"})

    questions_raw = q_resp.json().get("docs", []) if isinstance(q_resp.json(), dict) else []
    categories_raw: List[Dict[str, Any]] = []
    if not isinstance(c_resp, Exception) and c_resp.status_code == 200:
        body = c_resp.json()
        categories_raw = body.get("docs", []) if isinstance(body, dict) else []
    else:
        # Categories are optional: the UI falls back to the flat grid.
        logger.info("categories fetch unavailable (%s); serving flat question list",
                    getattr(c_resp, "status_code", "exc"))

    questions: List[Dict[str, Any]] = []
    for d in questions_raw:
        if not isinstance(d, dict):
            continue
        text = _localized(d.get("question"), locale).strip()
        if not text:
            continue
        questions.append(
            {
                "id": str(d.get("id") or ""),
                "question": text,
                "order": int(d.get("order") or 0),
                "isActive": bool(d.get("isActive", True)),
                "categoryId": _relation_id(d.get("category")),
            }
        )
    questions.sort(key=lambda q: q["order"])

    active_counts: Dict[str, int] = {}
    for q in questions:
        if q["isActive"] and q["categoryId"]:
            active_counts[q["categoryId"]] = active_counts.get(q["categoryId"], 0) + 1

    categories: List[Dict[str, Any]] = []
    for c in categories_raw:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        cid = str(c["id"])
        categories.append(
            {
                "id": cid,
                "name": _localized(c.get("name"), locale) or "Untitled",
                "description": _localized(c.get("description"), locale) or None,
                "icon": c.get("icon") if isinstance(c.get("icon"), str) else None,
                "audienceLevel": c.get("audienceLevel") if isinstance(c.get("audienceLevel"), str) else None,
                "order": int(c.get("order") or 0),
                "parentId": _relation_id(c.get("parent")),
                "questionCount": active_counts.get(cid, 0),
            }
        )
    categories.sort(key=lambda c: (c["order"], c["name"]))

    out = {"categories": categories, "questions": questions}
    _cache[locale] = (now, out)
    return out


async def _gather(*aws):
    return await asyncio.gather(*aws, return_exceptions=True)


async def _cached_flags(questions: List[Dict[str, Any]]) -> Dict[str, bool]:
    """Which questions already have a pre-generated answer in the suggested-question cache."""
    try:
        from backend.cache_utils import suggested_question_cache

        texts = [q["question"] for q in questions]
        if hasattr(suggested_question_cache, "cached_flags"):
            return await suggested_question_cache.cached_flags(texts)
        return {t: await suggested_question_cache.is_cached(t) for t in texts}
    except Exception as e:  # noqa: BLE001
        logger.debug("cached_flags lookup failed: %s", e)
        return {}


@router.get("/suggested-questions")
async def list_suggested_questions(
    request: Request,
    response: Response,
    category: Optional[str] = Query(None, description="Only questions in this category id"),
    locale: str = Query("en", description="Content locale (en, es, fr)"),
) -> Dict[str, Any]:
    await check_rate_limit(request, SUGGESTED_QUESTIONS_RATE_LIMIT)
    loc = locale if locale in _ALLOWED_LOCALES else "en"

    data = await _fetch_cms(loc)
    questions = list(data["questions"])
    if category:
        questions = [q for q in questions if q["categoryId"] == category]

    flags = await _cached_flags(questions)
    questions = [{**q, "cached": bool(flags.get(q["question"], False))} for q in questions]

    response.headers["Cache-Control"] = "public, max-age=30"
    return {"categories": data["categories"], "questions": questions, "fallback": False}
