"""Enqueue ARQ jobs. API and scripts call these; they do not run the work."""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend.jobs.redis_settings import redis_settings_from_env

logger = logging.getLogger(__name__)

_pool = None


async def _get_pool():
    global _pool
    if _pool is None:
        from arq import create_pool

        _pool = await create_pool(redis_settings_from_env("redis://localhost:6379/0"))
    return _pool


async def enqueue_job(function_name: str, *args: Any, **kwargs: Any) -> str:
    pool = await _get_pool()
    job = await pool.enqueue_job(function_name, *args, **kwargs)
    job_id = job.job_id if job else "unknown"
    logger.info("Enqueued %s job_id=%s", function_name, job_id)
    return job_id


async def enqueue_ingest(doc_dict: Dict[str, Any], operation: str) -> str:
    return await enqueue_job("ingest_payload_document", doc_dict, operation)


async def enqueue_delete(payload_id: str, operation: str) -> str:
    return await enqueue_job("delete_payload_document", payload_id, operation)


async def enqueue_reindex(with_faq: bool = False) -> str:
    name = "reindex_with_faq" if with_faq else "reindex_vectors"
    return await enqueue_job(name)


async def enqueue_refresh_suggested() -> str:
    return await enqueue_job("refresh_suggested_questions")


async def enqueue_cleanup_orphans() -> str:
    return await enqueue_job("cleanup_orphans")


MAINTENANCE_JOBS = (
    "flag_stale_articles",
    "run_golden_eval",
    "cluster_gap_candidates",
    "reconcile_embeddings",
    "ingest_doc_sources",
    "reingest_all_published",  # on-demand only (not scheduled)
)


async def enqueue_maintenance(name: str) -> str:
    """Enqueue one of the scheduled maintenance jobs on demand (admin Jobs page)."""
    if name not in MAINTENANCE_JOBS:
        raise ValueError(f"Unknown maintenance job: {name!r}")
    return await enqueue_job(name)
