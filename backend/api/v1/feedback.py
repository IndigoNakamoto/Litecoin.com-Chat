"""
Reader feedback (thumbs up/down) on cited answers.

Public:  POST /api/v1/chat/feedback      — store a verdict, filed against the cited source docs.
Admin:   GET  /api/v1/admin/feedback      — recent feedback, newest first.
         GET  /api/v1/admin/feedback/by-source — thumbs-down counts grouped by Payload article.

A thumbs-down is attributed to the documents that were cited, not to the model:
most "wrong answers" are stale or missing chunks, and the by-source view is what
the Friday stale-doc review reads.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from backend.data_models import AnswerFeedback, AnswerFeedbackRequest
from backend.dependencies import get_answer_feedback_collection, get_llm_request_logs_collection
from backend.rate_limiter import RateLimitConfig, check_rate_limit

logger = logging.getLogger(__name__)

public_router = APIRouter()
admin_router = APIRouter()

FEEDBACK_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=int(os.getenv("FEEDBACK_RATE_LIMIT_PER_MINUTE", "20")),
    requests_per_hour=int(os.getenv("FEEDBACK_RATE_LIMIT_PER_HOUR", "200")),
    identifier="chat_feedback",
)

ADMIN_FEEDBACK_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=60,
    requests_per_hour=500,
    identifier="admin_feedback",
    enable_progressive_limits=False,
)


def _verify_admin(request: Request) -> None:
    auth = request.headers.get("Authorization") or ""
    try:
        scheme, token = auth.split(" ", 1)
    except ValueError:
        scheme, token = "", ""
    expected = os.getenv("ADMIN_TOKEN")
    if scheme.lower() != "bearer" or not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail={"error": "Unauthorized", "message": "Invalid or missing admin token"})


def _fingerprint_hash(request: Request) -> Optional[str]:
    raw = request.headers.get("X-Fingerprint")
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@public_router.post("/chat/feedback", status_code=202)
async def submit_feedback(payload: AnswerFeedbackRequest, request: Request) -> Dict[str, Any]:
    """Record a thumbs up/down. Idempotent per (request_id, fingerprint)."""
    await check_rate_limit(request, FEEDBACK_RATE_LIMIT)

    fp_hash = _fingerprint_hash(request)
    user_question: Optional[str] = None
    try:
        logs = await get_llm_request_logs_collection()
        log_doc = await logs.find_one({"request_id": payload.request_id}, {"user_question": 1, "source_payload_ids": 1})
        if log_doc:
            user_question = log_doc.get("user_question")
            # Prefer the server-side record of what was cited over the client's claim.
            logged_ids = log_doc.get("source_payload_ids") or []
            if logged_ids:
                payload.source_payload_ids = [str(x) for x in logged_ids]
    except Exception as e:  # noqa: BLE001
        logger.debug("Feedback: could not look up request log %s: %s", payload.request_id, e)

    record = AnswerFeedback(
        request_id=payload.request_id,
        verdict=payload.verdict,
        reason=payload.reason,
        comment=payload.comment,
        source_payload_ids=payload.source_payload_ids,
        user_question=user_question,
        fingerprint_hash=fp_hash,
    )

    try:
        collection = await get_answer_feedback_collection()
        selector: Dict[str, Any] = {"request_id": payload.request_id}
        if fp_hash:
            selector["fingerprint_hash"] = fp_hash
        await collection.update_one(selector, {"$set": record.model_dump(exclude={"id"})}, upsert=True)
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to store answer feedback: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail={"error": "Feedback store unavailable"})

    try:
        from backend.monitoring.metrics import answer_feedback_total

        answer_feedback_total.labels(verdict=payload.verdict).inc()
    except Exception:
        pass

    return {"status": "recorded", "request_id": payload.request_id, "verdict": payload.verdict}


@admin_router.get("/feedback")
async def list_feedback(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    verdict: Optional[str] = Query(None, pattern="^(up|down)$"),
    days: int = Query(30, ge=1, le=365),
) -> Dict[str, Any]:
    await check_rate_limit(request, ADMIN_FEEDBACK_RATE_LIMIT)
    _verify_admin(request)
    collection = await get_answer_feedback_collection()
    since = datetime.utcnow() - timedelta(days=days)
    query: Dict[str, Any] = {"timestamp": {"$gte": since}}
    if verdict:
        query["verdict"] = verdict
    items: List[Dict[str, Any]] = []
    async for doc in collection.find(query).sort("timestamp", -1).limit(limit):
        doc["id"] = str(doc.pop("_id"))
        ts = doc.get("timestamp")
        if hasattr(ts, "isoformat"):
            doc["timestamp"] = ts.isoformat()
        items.append(doc)
    total_up = await collection.count_documents({**query, "verdict": "up"}) if not verdict else None
    total_down = await collection.count_documents({**query, "verdict": "down"}) if not verdict else None
    return {"items": items, "count": len(items), "totals": {"up": total_up, "down": total_down}, "days": days}


@admin_router.get("/feedback/by-source")
async def feedback_by_source(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    """Thumbs-down (and up) counts per cited Payload article, worst first."""
    await check_rate_limit(request, ADMIN_FEEDBACK_RATE_LIMIT)
    _verify_admin(request)
    collection = await get_answer_feedback_collection()
    since = datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {"timestamp": {"$gte": since}, "source_payload_ids": {"$exists": True, "$ne": []}}},
        {"$unwind": "$source_payload_ids"},
        {
            "$group": {
                "_id": "$source_payload_ids",
                "down": {"$sum": {"$cond": [{"$eq": ["$verdict", "down"]}, 1, 0]}},
                "up": {"$sum": {"$cond": [{"$eq": ["$verdict", "up"]}, 1, 0]}},
                "reasons": {"$push": "$reason"},
                "last_feedback": {"$max": "$timestamp"},
                "sample_questions": {"$addToSet": "$user_question"},
            }
        },
        {"$sort": {"down": -1, "up": 1}},
        {"$limit": limit},
    ]
    rows: List[Dict[str, Any]] = []
    async for row in collection.aggregate(pipeline):
        reasons = [r for r in (row.get("reasons") or []) if r]
        reason_counts: Dict[str, int] = {}
        for r in reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1
        last = row.get("last_feedback")
        rows.append(
            {
                "payload_id": row["_id"],
                "down": row.get("down", 0),
                "up": row.get("up", 0),
                "reasons": reason_counts,
                "last_feedback": last.isoformat() if hasattr(last, "isoformat") else last,
                "sample_questions": [q for q in (row.get("sample_questions") or []) if q][:5],
            }
        )
    return {"items": rows, "days": days}
