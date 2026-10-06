"""Job enqueue endpoints do not execute work in the API process."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _jobs_client(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    from backend.api.v1.admin import jobs as jobs_mod

    app = FastAPI()
    app.include_router(jobs_mod.router, prefix="/api/v1/admin")
    return TestClient(app)


def test_reindex_enqueues(monkeypatch):
    enqueue = AsyncMock(return_value="job-123")
    monkeypatch.setattr("backend.api.v1.admin.jobs.enqueue_reindex", enqueue)
    http = _jobs_client(monkeypatch)
    response = http.post(
        "/api/v1/admin/jobs/reindex",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["job_id"] == "job-123"
    enqueue.assert_awaited()


def test_reindex_requires_admin(monkeypatch):
    http = _jobs_client(monkeypatch)
    response = http.post("/api/v1/admin/jobs/reindex")
    assert response.status_code == 401


def test_redis_settings_omits_empty_username(monkeypatch):
    pytest.importorskip("arq")
    monkeypatch.setenv("REDIS_URL", "redis://:secret%2Bpass@redis:6379/2")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    from backend.jobs.redis_settings import redis_settings_from_env

    settings = redis_settings_from_env()
    assert settings.host == "redis"
    assert settings.port == 6379
    assert settings.database == 2
    assert settings.username is None
    assert settings.password == "secret+pass"


def test_worker_registers_ingest_with_long_timeout_and_retry(monkeypatch):
    """Ingest can outlive ARQ's 300 s default; the Oct 5 bulk publish lost 3 articles to it."""
    pytest.importorskip("arq")
    import importlib

    monkeypatch.delenv("INGEST_JOB_TIMEOUT_S", raising=False)
    monkeypatch.delenv("ARQ_MAX_JOBS", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    import backend.jobs.worker as worker_mod

    def registered(mod):
        # `func(...)` entries carry .name/.timeout_s; bare coroutine entries do not.
        return {getattr(f, "name", getattr(f, "__name__", None)): f for f in mod.WorkerSettings.functions}

    worker_mod = importlib.reload(worker_mod)
    by_name = registered(worker_mod)
    assert by_name["ingest_payload_document"].timeout_s >= 1800
    assert by_name["ingest_payload_document"].max_tries == 2
    assert by_name["delete_payload_document"].timeout_s >= 1800
    assert worker_mod.WorkerSettings.max_jobs == 2

    monkeypatch.setenv("INGEST_JOB_TIMEOUT_S", "3600")
    monkeypatch.setenv("ARQ_MAX_JOBS", "3")
    worker_mod = importlib.reload(worker_mod)
    assert registered(worker_mod)["ingest_payload_document"].timeout_s == 3600
    assert worker_mod.WorkerSettings.max_jobs == 3

    # Below the floor is clamped, never silently back to ARQ's default.
    monkeypatch.setenv("INGEST_JOB_TIMEOUT_S", "10")
    worker_mod = importlib.reload(worker_mod)
    assert registered(worker_mod)["ingest_payload_document"].timeout_s == 300


@pytest.mark.asyncio
async def test_ingest_task_raises_when_published_article_has_no_chunks(monkeypatch):
    import asyncio

    from backend.jobs import tasks

    doc = {
        "id": "abc123",
        "createdAt": "2026-10-05T00:00:00Z",
        "updatedAt": "2026-10-05T00:00:00Z",
        "title": "LDK README",
        "content": {},
        "markdown": "# LDK",
        "status": "published",
    }
    monkeypatch.setattr("backend.api.v1.sync.payload.process_and_embed_document", lambda *_a, **_k: None)

    monkeypatch.setattr(tasks, "_stored_chunk_count", lambda _pid: 0)
    with pytest.raises(tasks.IngestProducedNoChunks):
        await tasks.ingest_payload_document({}, doc, "create")

    monkeypatch.setattr(tasks, "_stored_chunk_count", lambda _pid: 17)
    assert await tasks.ingest_payload_document({}, doc, "update") == {"payload_id": "abc123", "status": "published", "chunks": 17}

    # Could not check (Mongo down): report None, do not fail the job on a guess.
    monkeypatch.setattr(tasks, "_stored_chunk_count", lambda _pid: None)
    assert (await tasks.ingest_payload_document({}, doc, "update"))["chunks"] is None

    # Drafts/unpublish never carry chunks; no count, no error.
    monkeypatch.setattr(tasks, "_stored_chunk_count", lambda _pid: (_ for _ in ()).throw(AssertionError("must not count")))
    out = await tasks.ingest_payload_document({}, {**doc, "status": "draft"}, "update")
    assert out["chunks"] is None and out["status"] == "draft"
    await asyncio.sleep(0)


def test_redis_settings_prefers_raw_password_env(monkeypatch):
    pytest.importorskip("arq")
    monkeypatch.setenv("REDIS_URL", "redis://:ignored@redis:6379/0")
    monkeypatch.setenv("REDIS_PASSWORD", "raw-password")
    from backend.jobs.redis_settings import redis_settings_from_env

    settings = redis_settings_from_env()
    assert settings.username is None
    assert settings.password == "raw-password"
