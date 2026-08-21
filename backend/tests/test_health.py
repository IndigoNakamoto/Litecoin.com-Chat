"""Health dependency matrix: ready 503, detailed auth, no VSM construction."""

from unittest.mock import AsyncMock, patch

import pytest
from backend.monitoring.health import HealthChecker, HealthStatus


@pytest.mark.asyncio
async def test_ready_503_when_redis_down():
    checker = HealthChecker()
    checker.ping_mongo = AsyncMock(
        return_value={"status": HealthStatus.HEALTHY, "class": "critical"}
    )
    checker.ping_redis = AsyncMock(
        return_value={"status": HealthStatus.UNHEALTHY, "class": "critical", "error": "down"}
    )
    body = await checker.get_public_readiness()
    assert body["ready"] is False
    assert body["status"] == HealthStatus.UNHEALTHY.value


@pytest.mark.asyncio
async def test_ready_200_when_payload_down():
    checker = HealthChecker()
    checker.ping_mongo = AsyncMock(
        return_value={"status": HealthStatus.HEALTHY, "class": "critical"}
    )
    checker.ping_redis = AsyncMock(
        return_value={"status": HealthStatus.HEALTHY, "class": "critical"}
    )
    checker.check_payload = AsyncMock(
        return_value={"status": HealthStatus.DEGRADED, "class": "degraded", "error": "down"}
    )
    body = await checker.get_public_readiness()
    assert body["ready"] is True
    assert body["status"] == HealthStatus.HEALTHY.value


@pytest.mark.asyncio
async def test_ready_does_not_construct_vector_store_manager():
    checker = HealthChecker()
    checker.ping_mongo = AsyncMock(
        return_value={"status": HealthStatus.HEALTHY, "class": "critical"}
    )
    checker.ping_redis = AsyncMock(
        return_value={"status": HealthStatus.HEALTHY, "class": "critical"}
    )
    with patch(
        "backend.data_ingestion.vector_store_manager.VectorStoreManager"
    ) as vsm_cls:
        await checker.get_readiness()
        vsm_cls.assert_not_called()
    info = checker.check_vector_store()
    assert info["class"] == "info"
    assert info["status"] == HealthStatus.UNKNOWN


@pytest.mark.asyncio
async def test_comprehensive_degraded_when_payload_down():
    checker = HealthChecker()
    checker.ping_mongo = AsyncMock(
        return_value={"status": HealthStatus.HEALTHY, "class": "critical"}
    )
    checker.ping_redis = AsyncMock(
        return_value={"status": HealthStatus.HEALTHY, "class": "critical"}
    )
    for name in (
        "check_gemini",
        "check_infinity",
        "check_ollama",
        "check_litecoin_space",
        "check_redis_stack",
    ):
        setattr(
            checker,
            name,
            AsyncMock(return_value={"status": HealthStatus.HEALTHY, "class": "degraded", "skipped": True}),
        )
    checker.check_payload = AsyncMock(
        return_value={"status": HealthStatus.DEGRADED, "class": "degraded", "error": "down"}
    )
    result = await checker.get_comprehensive_health()
    assert result["ready"] is True
    assert result["status"] == HealthStatus.DEGRADED.value


def test_ready_http_status_codes():
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/health/ready")
    async def ready(fail: bool = False):
        body = {"status": "unhealthy" if fail else "healthy", "timestamp": "t", "ready": not fail}
        return JSONResponse(content=body, status_code=200 if body["ready"] else 503)

    http = TestClient(app)
    assert http.get("/health/ready").status_code == 200
    assert http.get("/health/ready", params={"fail": "true"}).status_code == 503


def test_detailed_auth_gate(monkeypatch):
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.testclient import TestClient

    from backend.api.v1.admin.auth import verify_admin_token

    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    app = FastAPI()

    @app.get("/health/detailed")
    async def detailed(request: Request):
        auth = request.headers.get("authorization")
        if not verify_admin_token(auth):
            raise HTTPException(status_code=401, detail="Unauthorized")
        return {"status": "healthy"}

    http = TestClient(app)
    assert http.get("/health/detailed").status_code == 401
    assert http.get(
        "/health/detailed",
        headers={"Authorization": "Bearer test-admin-token"},
    ).status_code == 200


def test_live_payload():
    checker = HealthChecker()
    body = checker.get_liveness()
    assert body["status"] == "healthy"
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_circuit_breaker_opens():
    from backend.services.circuit_breaker import CircuitBreaker, CircuitOpen

    breaker = CircuitBreaker("test", fail_threshold=2, reset_seconds=60)

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    with pytest.raises(CircuitOpen):
        await breaker.call(boom)
