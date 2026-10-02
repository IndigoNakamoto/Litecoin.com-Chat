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


@router.post("/jobs/reload-index")
async def reload_vector_index(request: Request) -> Dict[str, Any]:
    """Reload the FAISS index from disk into this API process (after a worker reindex)."""
    _require_admin(request)
    from backend.api.v1.sync.payload import _global_rag_pipeline

    if _global_rag_pipeline is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialised")
    try:
        _global_rag_pipeline.refresh_vector_store()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Reload failed: {e}")
    vsm = getattr(_global_rag_pipeline, "vector_store_manager", None)
    count = None
    try:
        idx = getattr(getattr(vsm, "vector_store", None), "index", None)
        count = int(idx.ntotal) if idx is not None else None
    except Exception:
        pass
    return {"status": "reloaded", "vectors": count}


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
