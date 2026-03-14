"""
Admin API endpoints for managing knowledge gap candidates.

Candidates are created automatically when search grounding fills KB gaps.
Admins can review, approve, reject, or publish them as Payload CMS draft articles.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field
import logging
import os
import hmac

from backend.dependencies import get_knowledge_candidates_collection
from backend.rate_limiter import RateLimitConfig, check_rate_limit
from bson import ObjectId

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_CANDIDATES_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=60,
    requests_per_hour=500,
    identifier="admin_knowledge_candidates",
    enable_progressive_limits=False,
)


def _verify_admin_token(authorization: Optional[str]) -> bool:
    if not authorization:
        return False
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            return False
    except ValueError:
        return False
    expected_token = os.getenv("ADMIN_TOKEN")
    if not expected_token:
        logger.warning("ADMIN_TOKEN not set, admin endpoint authentication disabled")
        return False
    return hmac.compare_digest(token, expected_token)


def _require_admin(request: Request) -> None:
    auth_header = request.headers.get("Authorization")
    if not _verify_admin_token(auth_header):
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"},
        )


def _serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable dict."""
    result = dict(doc)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    # Drop embedding from list responses (large payload)
    result.pop("question_embedding", None)
    if "timestamp" in result and hasattr(result["timestamp"], "isoformat"):
        result["timestamp"] = result["timestamp"].isoformat() + "Z"
    if "reviewed_at" in result and result["reviewed_at"] and hasattr(result["reviewed_at"], "isoformat"):
        result["reviewed_at"] = result["reviewed_at"].isoformat() + "Z"
    return result


class CandidateUpdateRequest(BaseModel):
    status: Optional[Literal["approved", "rejected"]] = None
    admin_notes: Optional[str] = None


@router.get("/knowledge-candidates")
async def list_knowledge_candidates(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, published"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("question_frequency", description="Sort field"),
    sort_order: int = Query(-1, description="-1 for descending, 1 for ascending"),
) -> Dict[str, Any]:
    """List knowledge gap candidates with pagination and filtering."""
    await check_rate_limit(request, ADMIN_CANDIDATES_RATE_LIMIT)
    _require_admin(request)

    try:
        collection = await get_knowledge_candidates_collection()
        query_filter: Dict[str, Any] = {}
        if status:
            query_filter["status"] = status

        total = await collection.count_documents(query_filter)

        cursor = (
            collection.find(query_filter, {"question_embedding": 0})
            .sort(sort_by, sort_order)
            .skip(offset)
            .limit(limit)
        )

        candidates = []
        async for doc in cursor:
            candidates.append(_serialize_doc(doc))

        return {
            "candidates": candidates,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error("Error listing knowledge candidates: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Failed to list candidates"})


@router.get("/knowledge-candidates/stats")
async def get_knowledge_candidates_stats(request: Request) -> Dict[str, Any]:
    """Get aggregated statistics for knowledge gap candidates."""
    await check_rate_limit(request, ADMIN_CANDIDATES_RATE_LIMIT)
    _require_admin(request)

    try:
        collection = await get_knowledge_candidates_collection()

        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total_frequency": {"$sum": "$question_frequency"},
                }
            }
        ]
        status_counts: Dict[str, Dict[str, int]] = {}
        async for doc in collection.aggregate(pipeline):
            status_counts[doc["_id"]] = {
                "count": doc["count"],
                "total_frequency": doc["total_frequency"],
            }

        topic_pipeline = [
            {"$match": {"status": "pending"}},
            {"$group": {"_id": "$topic_cluster", "count": {"$sum": 1}, "total_frequency": {"$sum": "$question_frequency"}}},
            {"$sort": {"total_frequency": -1}},
            {"$limit": 20},
        ]
        top_topics = []
        async for doc in collection.aggregate(topic_pipeline):
            top_topics.append({
                "topic": doc["_id"] or "uncategorized",
                "count": doc["count"],
                "total_frequency": doc["total_frequency"],
            })

        return {
            "by_status": status_counts,
            "top_pending_topics": top_topics,
            "total_candidates": sum(s["count"] for s in status_counts.values()),
        }
    except Exception as e:
        logger.error("Error getting knowledge candidates stats: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Failed to get stats"})


@router.get("/knowledge-candidates/{candidate_id}")
async def get_knowledge_candidate(request: Request, candidate_id: str) -> Dict[str, Any]:
    """Get a single knowledge gap candidate with full details."""
    await check_rate_limit(request, ADMIN_CANDIDATES_RATE_LIMIT)
    _require_admin(request)

    try:
        collection = await get_knowledge_candidates_collection()
        doc = await collection.find_one({"_id": ObjectId(candidate_id)})
        if not doc:
            raise HTTPException(status_code=404, detail={"error": "Candidate not found"})
        return {"candidate": _serialize_doc(doc)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting knowledge candidate %s: %s", candidate_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Failed to get candidate"})


@router.patch("/knowledge-candidates/{candidate_id}")
async def update_knowledge_candidate(
    request: Request,
    candidate_id: str,
    update: CandidateUpdateRequest,
) -> Dict[str, Any]:
    """Update a knowledge gap candidate (approve/reject, add notes)."""
    await check_rate_limit(request, ADMIN_CANDIDATES_RATE_LIMIT)
    _require_admin(request)

    try:
        collection = await get_knowledge_candidates_collection()
        update_fields: Dict[str, Any] = {"reviewed_at": datetime.utcnow()}

        if update.status:
            update_fields["status"] = update.status
        if update.admin_notes is not None:
            update_fields["admin_notes"] = update.admin_notes

        result = await collection.update_one(
            {"_id": ObjectId(candidate_id)},
            {"$set": update_fields},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail={"error": "Candidate not found"})

        # Track metrics
        try:
            if update.status == "approved":
                from backend.monitoring.metrics import knowledge_candidates_approved_total
                knowledge_candidates_approved_total.inc()
            elif update.status == "rejected":
                from backend.monitoring.metrics import knowledge_candidates_rejected_total
                knowledge_candidates_rejected_total.inc()
        except ImportError:
            pass

        updated_doc = await collection.find_one({"_id": ObjectId(candidate_id)})
        return {"candidate": _serialize_doc(updated_doc) if updated_doc else {}, "updated": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating knowledge candidate %s: %s", candidate_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Failed to update candidate"})


class CandidatePublishRequest(BaseModel):
    publish_status: Literal["draft", "published"] = Field(
        default="draft",
        description="CMS article status: 'draft' to edit later, 'published' to go live immediately",
    )


@router.post("/knowledge-candidates/{candidate_id}/publish")
async def publish_knowledge_candidate(
    request: Request,
    candidate_id: str,
    body: Optional[CandidatePublishRequest] = None,
) -> Dict[str, Any]:
    """
    Create a Payload CMS article from an approved candidate.

    Accepts an optional JSON body with ``publish_status`` (default "draft").
    When set to "published", the article goes live immediately and the
    existing afterChange webhook syncs it into the vector store.
    """
    await check_rate_limit(request, ADMIN_CANDIDATES_RATE_LIMIT)
    _require_admin(request)

    publish_status = (body.publish_status if body else "draft")

    try:
        collection = await get_knowledge_candidates_collection()
        doc = await collection.find_one({"_id": ObjectId(candidate_id)})
        if not doc:
            raise HTTPException(status_code=404, detail={"error": "Candidate not found"})

        if doc.get("status") == "published":
            raise HTTPException(status_code=409, detail={"error": "Candidate already published"})

        from backend.services.article_draft_generator import create_payload_draft

        payload_article_id = await create_payload_draft(
            question=doc["user_question"],
            answer=doc["generated_answer"],
            topic=doc.get("topic_cluster"),
            grounding_sources=doc.get("grounding_sources", []),
            publish_status=publish_status,
        )

        await collection.update_one(
            {"_id": ObjectId(candidate_id)},
            {
                "$set": {
                    "status": "published",
                    "payload_article_id": payload_article_id,
                    "cms_publish_status": publish_status,
                    "reviewed_at": datetime.utcnow(),
                }
            },
        )

        try:
            from backend.monitoring.metrics import knowledge_candidates_published_total
            knowledge_candidates_published_total.inc()
        except ImportError:
            pass

        return {
            "published": True,
            "payload_article_id": payload_article_id,
            "candidate_id": candidate_id,
            "cms_status": publish_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error publishing knowledge candidate %s: %s", candidate_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Failed to publish candidate"})
