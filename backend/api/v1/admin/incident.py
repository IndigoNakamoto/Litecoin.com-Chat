"""
Admin endpoints for the incident override pin.

GET    /api/v1/admin/incident-pin   -> current pin or {"active": false}
PUT    /api/v1/admin/incident-pin   -> set / replace the pin
DELETE /api/v1/admin/incident-pin   -> clear it
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from backend.rate_limiter import RateLimitConfig, check_rate_limit
from backend.services.incident_pin import IncidentPinCreate, clear_pin, get_pin, set_pin
from backend.utils.admin_auth import admin_operator

logger = logging.getLogger(__name__)
router = APIRouter()

ADMIN_INCIDENT_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=30,
    requests_per_hour=200,
    identifier="admin_incident",
    enable_progressive_limits=False,
)


def _verify_admin(request: Request) -> str:
    """Raise 401 unless the bearer token is valid; return the operator name for log lines."""
    operator = admin_operator(request.headers.get("Authorization"))
    if operator is None:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized", "message": "Invalid or missing admin token"})
    return operator


async def _redis():
    from backend.redis_client import get_redis_client

    try:
        return await get_redis_client()
    except Exception as e:  # noqa: BLE001
        logger.error("Redis unavailable for incident pin: %s", e)
        raise HTTPException(status_code=503, detail={"error": "Redis unavailable"})


def _serialize(pin) -> Dict[str, Any]:
    data = pin.model_dump(mode="json")
    data["active"] = True
    return data


@router.get("/incident-pin")
async def read_incident_pin(request: Request) -> Dict[str, Any]:
    await check_rate_limit(request, ADMIN_INCIDENT_RATE_LIMIT)
    _verify_admin(request)
    pin = await get_pin(await _redis())
    if pin is None:
        return {"active": False}
    return _serialize(pin)


@router.put("/incident-pin")
async def write_incident_pin(payload: IncidentPinCreate, request: Request) -> Dict[str, Any]:
    await check_rate_limit(request, ADMIN_INCIDENT_RATE_LIMIT)
    operator = _verify_admin(request)
    pin = await set_pin(await _redis(), payload)
    logger.info("Admin set incident pin id=%s operator=%s", getattr(pin, "id", None), operator)
    return _serialize(pin)


@router.delete("/incident-pin")
async def delete_incident_pin(request: Request) -> Dict[str, Any]:
    await check_rate_limit(request, ADMIN_INCIDENT_RATE_LIMIT)
    operator = _verify_admin(request)
    removed = await clear_pin(await _redis())
    logger.info("Admin cleared incident pin removed=%s operator=%s", removed, operator)
    return {"active": False, "cleared": removed}
