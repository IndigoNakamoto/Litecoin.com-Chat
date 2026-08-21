"""ARQ worker settings. Run: arq backend.jobs.worker.WorkerSettings"""

from __future__ import annotations

import os

from backend.jobs.tasks import (
    cleanup_orphans,
    delete_payload_document,
    ingest_payload_document,
    refresh_suggested_questions,
    reindex_vectors,
    reindex_with_faq,
)


def _redis_settings():
    from arq.connections import RedisSettings

    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return RedisSettings.from_dsn(url)


class WorkerSettings:
    functions = [
        ingest_payload_document,
        delete_payload_document,
        reindex_vectors,
        reindex_with_faq,
        refresh_suggested_questions,
        cleanup_orphans,
    ]
    redis_settings = _redis_settings()
    max_jobs = 4
