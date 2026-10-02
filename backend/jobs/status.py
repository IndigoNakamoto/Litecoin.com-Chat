"""
Job run bookkeeping for scheduled maintenance.

Each cron job records start / finish / failure in two places:
- Redis hash `admin:jobs:status:<name>` (fast read for the admin Jobs page)
- Mongo collection `job_runs` (history, diffable by the golden-set runner)

Both writes are best-effort; a bookkeeping failure never fails the job.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATUS_KEY_PREFIX = os.getenv("JOB_STATUS_REDIS_PREFIX", "admin:jobs:status:")
JOB_RUNS_COLLECTION_NAME = os.getenv("JOB_RUNS_COLLECTION_NAME", "job_runs")

# Registry of scheduled jobs: name -> human schedule. Kept here (not in worker.py)
# so the admin API can list it without importing arq.
SCHEDULED_JOBS: Dict[str, Dict[str, str]] = {
    "flag_stale_articles": {"schedule": "nightly 03:15 UTC", "description": "Flag published articles past their review window"},
    "run_golden_eval": {"schedule": "nightly 03:45 UTC", "description": "Run the golden question set; alert on citation miss, abstain/refuse failure, regression"},
    "cluster_gap_candidates": {"schedule": "daily 04:15 UTC", "description": "Collapse repeated knowledge gaps into one draft each"},
    "reconcile_embeddings": {"schedule": "weekly Sun 04:45 UTC", "description": "Re-embed published articles missing from the vector store; drop orphans"},
    "ingest_doc_sources": {"schedule": "weekly Mon 05:15 UTC", "description": "Refresh Core / MWEB / Litecoin Space / litecoin.com reference drafts"},
    "reingest_all_published": {"schedule": "on demand", "description": "Re-chunk and re-embed every published article from Payload (after Article schema changes); then reload the index into the API"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _redis():
    try:
        from backend.redis_client import get_redis_client

        return await get_redis_client()
    except Exception as e:  # noqa: BLE001
        logger.debug("job status: redis unavailable: %s", e)
        return None


async def _runs_collection():
    try:
        from backend.dependencies import MONGO_DATABASE_NAME, get_mongo_client

        client = await get_mongo_client()
        if client is None:
            return None
        return client[MONGO_DATABASE_NAME][JOB_RUNS_COLLECTION_NAME]
    except Exception as e:  # noqa: BLE001
        logger.debug("job status: mongo unavailable: %s", e)
        return None


async def record_job_start(name: str) -> str:
    run_id = _now().strftime("%Y%m%dT%H%M%SZ")
    payload = {"name": name, "run_id": run_id, "status": "running", "started_at": _now().isoformat()}
    r = await _redis()
    if r is not None:
        try:
            await r.hset(f"{STATUS_KEY_PREFIX}{name}", mapping={k: json.dumps(v) for k, v in payload.items()})
        except Exception as e:  # noqa: BLE001
            logger.debug("job status start write failed: %s", e)
    return run_id


async def record_job_finish(
    name: str,
    run_id: str,
    status: str,
    summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    finished = _now()
    doc = {
        "name": name,
        "run_id": run_id,
        "status": status,
        "finished_at": finished,
        "summary": summary or {},
        "error": error,
    }
    r = await _redis()
    if r is not None:
        try:
            await r.hset(
                f"{STATUS_KEY_PREFIX}{name}",
                mapping={
                    "status": json.dumps(status),
                    "finished_at": json.dumps(finished.isoformat()),
                    "summary": json.dumps(summary or {}, default=str),
                    "error": json.dumps(error),
                    "run_id": json.dumps(run_id),
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("job status finish write failed: %s", e)
    coll = await _runs_collection()
    if coll is not None:
        try:
            await coll.insert_one(doc)
        except Exception as e:  # noqa: BLE001
            logger.debug("job run history write failed: %s", e)


async def get_job_statuses() -> List[Dict[str, Any]]:
    """Scheduled job registry merged with last-run state from Redis."""
    r = await _redis()
    out: List[Dict[str, Any]] = []
    for name, meta in SCHEDULED_JOBS.items():
        row: Dict[str, Any] = {"name": name, **meta, "last_status": None, "last_run": None, "summary": None, "error": None}
        if r is not None:
            try:
                raw = await r.hgetall(f"{STATUS_KEY_PREFIX}{name}")
                decoded = {}
                for k, v in (raw or {}).items():
                    k2 = k.decode() if isinstance(k, bytes) else k
                    v2 = v.decode() if isinstance(v, bytes) else v
                    try:
                        decoded[k2] = json.loads(v2)
                    except Exception:
                        decoded[k2] = v2
                row["last_status"] = decoded.get("status")
                row["last_run"] = decoded.get("finished_at") or decoded.get("started_at")
                row["summary"] = decoded.get("summary")
                row["error"] = decoded.get("error")
            except Exception as e:  # noqa: BLE001
                logger.debug("job status read failed for %s: %s", name, e)
        out.append(row)
    return out


async def get_last_run(name: str, status: Optional[str] = "success", before_run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Most recent stored run for a job (used by the eval runner to diff against last week)."""
    coll = await _runs_collection()
    if coll is None:
        return None
    query: Dict[str, Any] = {"name": name}
    if status:
        query["status"] = status
    if before_run_id:
        query["run_id"] = {"$lt": before_run_id}
    try:
        return await coll.find_one(query, sort=[("finished_at", -1)])
    except Exception as e:  # noqa: BLE001
        logger.debug("job last-run read failed: %s", e)
        return None
