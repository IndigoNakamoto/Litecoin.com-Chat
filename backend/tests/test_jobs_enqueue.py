"""Job enqueue endpoints do not execute work in the API process."""

from unittest.mock import AsyncMock

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
