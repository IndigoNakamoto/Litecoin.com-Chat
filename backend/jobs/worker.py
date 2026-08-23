"""ARQ worker settings. Run: arq backend.jobs.worker.WorkerSettings"""

from __future__ import annotations

from backend.jobs.redis_settings import redis_settings_from_env
from backend.jobs.tasks import (
    cleanup_orphans,
    delete_payload_document,
    ingest_payload_document,
    refresh_suggested_questions,
    reindex_vectors,
    reindex_with_faq,
)


class WorkerSettings:
    functions = [
        ingest_payload_document,
        delete_payload_document,
        reindex_vectors,
        reindex_with_faq,
        refresh_suggested_questions,
        cleanup_orphans,
    ]
    redis_settings = redis_settings_from_env()
    max_jobs = 4
