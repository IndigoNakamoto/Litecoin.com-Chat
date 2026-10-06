"""ARQ worker settings. Run: arq backend.jobs.worker.WorkerSettings

On-demand jobs (webhook / admin) plus the scheduled maintenance loop that
keeps one operator at ~3-4 hours a week:

    03:15 UTC daily   flag_stale_articles
    03:45 UTC daily   run_golden_eval
    04:15 UTC daily   cluster_gap_candidates
    04:45 UTC Sunday  reconcile_embeddings
    05:15 UTC Monday  ingest_doc_sources

Set DISABLE_CRON_JOBS=true to run a worker without the schedule (e.g. a second
replica, or local dev).

Article ingest (chunking + per-chunk FAQ generation) can run well past ARQ's
300 s default on long READMEs; INGEST_JOB_TIMEOUT_S (default 1800) and
ARQ_MAX_JOBS (default 2) are tuned so a bulk publish does not get cancelled
mid-flight while the `to_thread` work keeps running.
"""

from __future__ import annotations

import os

from arq import cron, func

from backend.jobs.maintenance import (
    cluster_gap_candidates,
    flag_stale_articles,
    ingest_doc_sources,
    reconcile_embeddings,
    reingest_all_published,
    run_golden_eval_job,
)
from backend.jobs.redis_settings import redis_settings_from_env
from backend.jobs.tasks import (
    cleanup_orphans,
    delete_payload_document,
    ingest_payload_document,
    refresh_suggested_questions,
    reindex_vectors,
    reindex_with_faq,
)

_CRON_DISABLED = os.getenv("DISABLE_CRON_JOBS", "false").lower() == "true"


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


INGEST_JOB_TIMEOUT_S = _env_int("INGEST_JOB_TIMEOUT_S", 1800, minimum=300)
ARQ_MAX_JOBS = _env_int("ARQ_MAX_JOBS", 2)


class WorkerSettings:
    functions = [
        # Job names are unchanged, so backend/jobs/enqueue.py keeps working.
        func(ingest_payload_document, name="ingest_payload_document", timeout=INGEST_JOB_TIMEOUT_S, max_tries=2),
        func(delete_payload_document, name="delete_payload_document", timeout=INGEST_JOB_TIMEOUT_S, max_tries=2),
        reindex_vectors,
        reindex_with_faq,
        refresh_suggested_questions,
        cleanup_orphans,
        # Maintenance jobs are also enqueueable on demand from the admin Jobs page.
        func(flag_stale_articles, name="flag_stale_articles", timeout=600),
        func(run_golden_eval_job, name="run_golden_eval", timeout=3600),
        func(cluster_gap_candidates, name="cluster_gap_candidates", timeout=1200),
        func(reconcile_embeddings, name="reconcile_embeddings", timeout=1200),
        func(ingest_doc_sources, name="ingest_doc_sources", timeout=3600),
        func(reingest_all_published, name="reingest_all_published", timeout=600),
    ]
    cron_jobs = (
        []
        if _CRON_DISABLED
        else [
            cron(flag_stale_articles, name="cron_flag_stale_articles", hour=3, minute=15, timeout=600),
            cron(run_golden_eval_job, name="cron_run_golden_eval", hour=3, minute=45, timeout=3600),
            cron(cluster_gap_candidates, name="cron_cluster_gap_candidates", hour=4, minute=15, timeout=1200),
            cron(reconcile_embeddings, name="cron_reconcile_embeddings", weekday=6, hour=4, minute=45, timeout=1200),
            cron(ingest_doc_sources, name="cron_ingest_doc_sources", weekday=0, hour=5, minute=15, timeout=3600),
        ]
    )
    redis_settings = redis_settings_from_env()
    max_jobs = ARQ_MAX_JOBS
