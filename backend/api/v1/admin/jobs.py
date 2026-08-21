"""Admin endpoints that enqueue background jobs. They do not execute work in-process."""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from backend.api.v1.admin.auth import verify_admin_token
from backend.jobs.enqueue import (
    enqueue_cleanup_orphans,
    enqueue_refresh_suggested,
    enqueue_reindex,
)

router = APIRouter()


def _require_admin(request: Request) -> None:
    if not verify_admin_token(request.headers.get("authorization")):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/jobs/reindex")
async def enqueue_reindex_job(request: Request) -> Dict[str, Any]:
    _require_admin(request)
    job_id = await enqueue_reindex(with_faq=False)
    return {"status": "queued", "job": "reindex_vectors", "job_id": job_id}


@router.post("/jobs/reindex-faq")
async def enqueue_reindex_faq_job(request: Request) -> Dict[str, Any]:
    _require_admin(request)
    job_id = await enqueue_reindex(with_faq=True)
    return {"status": "queued", "job": "reindex_with_faq", "job_id": job_id}


@router.post("/jobs/refresh-suggested")
async def enqueue_refresh_suggested_job(request: Request) -> Dict[str, Any]:
    _require_admin(request)
    job_id = await enqueue_refresh_suggested()
    return {"status": "queued", "job": "refresh_suggested_questions", "job_id": job_id}


@router.post("/jobs/cleanup-orphans")
async def enqueue_cleanup_job(request: Request) -> Dict[str, Any]:
    _require_admin(request)
    job_id = await enqueue_cleanup_orphans()
    return {"status": "queued", "job": "cleanup_orphans", "job_id": job_id}
