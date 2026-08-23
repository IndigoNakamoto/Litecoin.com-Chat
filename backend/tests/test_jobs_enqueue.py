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


def test_redis_settings_prefers_raw_password_env(monkeypatch):
    pytest.importorskip("arq")
    monkeypatch.setenv("REDIS_URL", "redis://:ignored@redis:6379/0")
    monkeypatch.setenv("REDIS_PASSWORD", "raw-password")
    from backend.jobs.redis_settings import redis_settings_from_env

    settings = redis_settings_from_env()
    assert settings.username is None
    assert settings.password == "raw-password"
