"""Admin endpoints that enqueue background jobs and report cron status. They do not execute work in-process."""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from backend.api.v1.admin.auth import verify_admin_token
from backend.jobs.enqueue import (
    MAINTENANCE_JOBS,
    enqueue_cleanup_orphans,
    enqueue_maintenance,
    enqueue_refresh_suggested,
    enqueue_reindex,
)
from backend.jobs.status import get_job_statuses

router = APIRouter()


def _require_admin(request: Request) -> None:
    if not verify_admin_token(request.headers.get("authorization")):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/jobs/status")
async def job_status(request: Request) -> Dict[str, Any]:
    """Scheduled jobs with their last run (status, time, summary)."""
    _require_admin(request)
    return {"jobs": await get_job_statuses()}


@router.post("/jobs/maintenance/{name}")
async def enqueue_maintenance_job(name: str, request: Request) -> Dict[str, Any]:
    """Run a scheduled maintenance job now."""
    _require_admin(request)
    if name not in MAINTENANCE_JOBS:
        raise HTTPException(status_code=404, detail=f"Unknown job {name!r}")
    try:
        job_id = await enqueue_maintenance(name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Could not enqueue: {e}")
    return {"status": "queued", "job": name, "job_id": job_id}


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
