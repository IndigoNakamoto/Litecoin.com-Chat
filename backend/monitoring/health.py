"""
Health checks as a dependency-class matrix.

Critical failures make /health/ready return 503.
Degraded failures keep the process ready but mark overall status degraded.
Info probes never affect readiness.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from backend.data_ingestion.vector_store_manager import VectorStoreManager

try:
    from backend.monitoring.metrics import (
        vector_store_documents_total,
        vector_store_health,
        dependency_health,
    )
    MONITORING_ENABLED = True
except ImportError:
    MONITORING_ENABLED = False

logger = logging.getLogger(__name__)

CRITICAL_PING_TIMEOUT = 0.2
DEGRADED_PING_TIMEOUT = 1.5
EXPENSIVE_PROBE_TTL_SECONDS = 60.0


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utcnow()).isoformat()


class HealthChecker:
    """Dependency-class health checker. Never constructs a VectorStoreManager."""

    def __init__(self, vector_store_manager: Optional[VectorStoreManager] = None):
        self.vector_store_manager = vector_store_manager
        self._last_check_time: Optional[datetime] = None
        self._last_check_result: Optional[Dict[str, Any]] = None
        self._probe_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def set_vector_store_manager(self, vector_store_manager: VectorStoreManager) -> None:
        self.vector_store_manager = vector_store_manager

    async def _cached_probe(
        self,
        name: str,
        factory: Callable[[], Awaitable[Dict[str, Any]]],
        ttl: float = EXPENSIVE_PROBE_TTL_SECONDS,
    ) -> Dict[str, Any]:
        now = time.monotonic()
        cached = self._probe_cache.get(name)
        if cached and (now - cached[0]) < ttl:
            result = dict(cached[1])
            result["cached"] = True
            return result
        result = await factory()
        self._probe_cache[name] = (now, result)
        return result

    async def ping_mongo(self, timeout: float = CRITICAL_PING_TIMEOUT) -> Dict[str, Any]:
        start = time.monotonic()
        try:
            from backend.dependencies import get_mongo_client

            client = await asyncio.wait_for(get_mongo_client(), timeout=timeout)
            await asyncio.wait_for(client.admin.command("ping"), timeout=timeout)
            return {
                "status": HealthStatus.HEALTHY,
                "class": "critical",
                "check_duration_seconds": time.monotonic() - start,
            }
        except Exception as e:
            logger.warning("Mongo ping failed: %s", e)
            return {
                "status": HealthStatus.UNHEALTHY,
                "class": "critical",
                "error": str(e),
                "check_duration_seconds": time.monotonic() - start,
            }

    async def ping_redis(self, timeout: float = CRITICAL_PING_TIMEOUT) -> Dict[str, Any]:
        start = time.monotonic()
        try:
            from backend.redis_client import get_redis_client

            client = await asyncio.wait_for(get_redis_client(), timeout=timeout)
            pong = await asyncio.wait_for(client.ping(), timeout=timeout)
            if not pong:
                raise RuntimeError("Redis ping returned falsy")
            return {
                "status": HealthStatus.HEALTHY,
                "class": "critical",
                "check_duration_seconds": time.monotonic() - start,
            }
        except Exception as e:
            logger.warning("Redis ping failed: %s", e)
            return {
                "status": HealthStatus.UNHEALTHY,
                "class": "critical",
                "error": str(e),
                "check_duration_seconds": time.monotonic() - start,
            }

    async def check_payload(self) -> Dict[str, Any]:
        url = os.getenv("PAYLOAD_PUBLIC_SERVER_URL") or os.getenv("PAYLOAD_URL")
        if not url:
            return {"status": HealthStatus.DEGRADED, "class": "degraded", "error": "PAYLOAD_PUBLIC_SERVER_URL not set"}
        start = time.monotonic()
        try:
            import httpx

            async with httpx.AsyncClient(timeout=DEGRADED_PING_TIMEOUT) as client:
                resp = await client.get(f"{url.rstrip('/')}/api/articles", params={"limit": 1})
            ok = 200 <= resp.status_code < 500
            return {
                "status": HealthStatus.HEALTHY if ok else HealthStatus.DEGRADED,
                "class": "degraded",
                "http_status": resp.status_code,
                "check_duration_seconds": time.monotonic() - start,
            }
        except Exception as e:
            return {
                "status": HealthStatus.DEGRADED,
                "class": "degraded",
                "error": str(e),
                "check_duration_seconds": time.monotonic() - start,
            }

    async def check_litecoin_space(self) -> Dict[str, Any]:
        base = os.getenv("LITECOIN_SPACE_API_URL", "https://litecoinspace.org/api").rstrip("/")
        start = time.monotonic()
        try:
            import httpx

            async with httpx.AsyncClient(timeout=DEGRADED_PING_TIMEOUT) as client:
                resp = await client.get(f"{base}/blocks/tip/height")
            ok = resp.status_code == 200
            return {
                "status": HealthStatus.HEALTHY if ok else HealthStatus.DEGRADED,
                "class": "degraded",
                "http_status": resp.status_code,
                "check_duration_seconds": time.monotonic() - start,
            }
        except Exception as e:
            return {
                "status": HealthStatus.DEGRADED,
                "class": "degraded",
                "error": str(e),
                "check_duration_seconds": time.monotonic() - start,
            }

    async def check_gemini(self) -> Dict[str, Any]:
        if not os.getenv("GOOGLE_API_KEY"):
            return {
                "status": HealthStatus.DEGRADED,
                "class": "degraded",
                "error": "GOOGLE_API_KEY not configured",
            }
        try:
            from backend.services.rewriter import GeminiRewriter

            rewriter = GeminiRewriter()
            ok = await asyncio.wait_for(rewriter.health_check(), timeout=DEGRADED_PING_TIMEOUT)
            return {
                "status": HealthStatus.HEALTHY if ok else HealthStatus.DEGRADED,
                "class": "degraded",
                "api_key_configured": True,
            }
        except Exception as e:
            return {
                "status": HealthStatus.DEGRADED,
                "class": "degraded",
                "api_key_configured": True,
                "error": str(e),
            }

    async def check_infinity(self) -> Dict[str, Any]:
        if os.getenv("USE_INFINITY_EMBEDDINGS", "false").lower() != "true":
            return {"status": HealthStatus.HEALTHY, "class": "degraded", "skipped": True}
        try:
            from backend.services.infinity_adapter import InfinityEmbeddings

            ok = await asyncio.wait_for(InfinityEmbeddings().health_check(), timeout=DEGRADED_PING_TIMEOUT)
            return {"status": HealthStatus.HEALTHY if ok else HealthStatus.DEGRADED, "class": "degraded"}
        except Exception as e:
            return {"status": HealthStatus.DEGRADED, "class": "degraded", "error": str(e)}

    async def check_ollama(self) -> Dict[str, Any]:
        if os.getenv("USE_LOCAL_REWRITER", "false").lower() != "true":
            return {"status": HealthStatus.HEALTHY, "class": "degraded", "skipped": True}
        try:
            from backend.services.rewriter import LocalRewriter

            ok = await asyncio.wait_for(LocalRewriter().health_check(), timeout=DEGRADED_PING_TIMEOUT)
            return {"status": HealthStatus.HEALTHY if ok else HealthStatus.DEGRADED, "class": "degraded"}
        except Exception as e:
            return {"status": HealthStatus.DEGRADED, "class": "degraded", "error": str(e)}

    async def check_redis_stack(self) -> Dict[str, Any]:
        if os.getenv("USE_REDIS_CACHE", "false").lower() != "true":
            return {"status": HealthStatus.HEALTHY, "class": "degraded", "skipped": True}
        try:
            from backend.services.redis_vector_cache import RedisVectorCache

            ok = await asyncio.wait_for(RedisVectorCache().health_check(), timeout=DEGRADED_PING_TIMEOUT)
            return {"status": HealthStatus.HEALTHY if ok else HealthStatus.DEGRADED, "class": "degraded"}
        except Exception as e:
            return {"status": HealthStatus.DEGRADED, "class": "degraded", "error": str(e)}

    def check_vector_store(self) -> Dict[str, Any]:
        """Info-only document counts. Never constructs a VectorStoreManager."""
        if self.vector_store_manager is None:
            logger.warning("Vector store metrics skipped: no shared VectorStoreManager")
            return {
                "status": HealthStatus.UNKNOWN,
                "class": "info",
                "error": "vector_store_manager not injected",
            }
        try:
            start_time = time.time()
            mongodb_available = self.vector_store_manager.mongodb_available
            total_count = published_count = draft_count = 0
            if mongodb_available:
                total_count = self.vector_store_manager.collection.count_documents({})
                published_count = self.vector_store_manager.collection.count_documents(
                    {"metadata.status": "published"}
                )
                draft_count = self.vector_store_manager.collection.count_documents(
                    {"metadata.status": "draft"}
                )
            if MONITORING_ENABLED:
                vector_store_documents_total.labels(status="total").set(total_count)
                vector_store_documents_total.labels(status="published").set(published_count)
                vector_store_documents_total.labels(status="draft").set(draft_count)
                vector_store_health.set(1 if mongodb_available else 0)
            return {
                "status": HealthStatus.HEALTHY if mongodb_available else HealthStatus.DEGRADED,
                "class": "info",
                "mongodb_available": mongodb_available,
                "document_counts": {
                    "total": total_count,
                    "published": published_count,
                    "draft": draft_count,
                },
                "check_duration_seconds": time.time() - start_time,
            }
        except Exception as e:
            logger.error("Vector store info check failed: %s", e, exc_info=True)
            return {"status": HealthStatus.DEGRADED, "class": "info", "error": str(e)}

    def check_cache(self) -> Dict[str, Any]:
        try:
            from backend.cache_utils import query_cache

            cache_stats = query_cache.stats()
            max_size = cache_stats.get("max_size", 1000) or 1000
            return {
                "status": HealthStatus.HEALTHY,
                "class": "info",
                "cache_size": cache_stats.get("size", 0),
                "cache_max_size": max_size,
                "cache_utilization": cache_stats.get("size", 0) / max_size,
            }
        except Exception as e:
            return {"status": HealthStatus.DEGRADED, "class": "info", "error": str(e)}

    def _set_dep_metric(self, name: str, dep_class: str, status: str) -> None:
        if not MONITORING_ENABLED:
            return
        value = 1 if status == HealthStatus.HEALTHY else 0
        try:
            dependency_health.labels(name=name, dep_class=dep_class).set(value)
        except Exception:
            pass

    async def get_readiness(self) -> Dict[str, Any]:
        mongo = await self.ping_mongo()
        redis = await self.ping_redis()
        self._set_dep_metric("mongo", "critical", mongo["status"])
        self._set_dep_metric("redis", "critical", redis["status"])
        ready = (
            mongo["status"] == HealthStatus.HEALTHY
            and redis["status"] == HealthStatus.HEALTHY
        )
        return {
            "status": HealthStatus.HEALTHY.value if ready else HealthStatus.UNHEALTHY.value,
            "timestamp": _iso(),
            "ready": ready,
            "critical": {"mongo": mongo, "redis": redis},
        }

    async def get_public_readiness(self) -> Dict[str, Any]:
        readiness = await self.get_readiness()
        return {
            "status": readiness["status"],
            "timestamp": readiness["timestamp"],
            "ready": readiness["ready"],
        }

    async def get_comprehensive_health(self) -> Dict[str, Any]:
        start = time.time()
        mongo, redis = await asyncio.gather(self.ping_mongo(), self.ping_redis())
        degraded = await asyncio.gather(
            self._cached_probe("gemini", self.check_gemini),
            self._cached_probe("infinity", self.check_infinity),
            self._cached_probe("ollama", self.check_ollama),
            self._cached_probe("payload", self.check_payload),
            self._cached_probe("litecoin_space", self.check_litecoin_space),
            self._cached_probe("redis_stack", self.check_redis_stack),
        )
        names = ("gemini", "infinity", "ollama", "payload", "litecoin_space", "redis_stack")
        degraded_map = dict(zip(names, degraded))
        info = {
            "vector_store": self.check_vector_store(),
            "in_process_cache": self.check_cache(),
            "langsmith_configured": bool(os.getenv("LANGCHAIN_API_KEY")),
        }

        critical_ok = mongo["status"] == HealthStatus.HEALTHY and redis["status"] == HealthStatus.HEALTHY
        any_degraded = any(
            d.get("status") == HealthStatus.DEGRADED and not d.get("skipped")
            for d in degraded_map.values()
        )
        if not critical_ok:
            overall = HealthStatus.UNHEALTHY
        elif any_degraded:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        self._set_dep_metric("mongo", "critical", mongo["status"])
        self._set_dep_metric("redis", "critical", redis["status"])
        for name, result in degraded_map.items():
            self._set_dep_metric(name, "degraded", result.get("status", HealthStatus.UNKNOWN))

        result = {
            "status": overall.value,
            "timestamp": _iso(),
            "check_duration_seconds": time.time() - start,
            "ready": critical_ok,
            "critical": {"mongo": mongo, "redis": redis},
            "degraded": degraded_map,
            "info": info,
        }
        self._last_check_time = _utcnow()
        self._last_check_result = result
        return result

    def get_liveness(self) -> Dict[str, Any]:
        return {"status": HealthStatus.HEALTHY.value, "timestamp": _iso()}

    async def get_public_health(self) -> Dict[str, Any]:
        readiness = await self.get_readiness()
        return {
            "status": readiness["status"],
            "timestamp": readiness["timestamp"],
        }


_health_checker: Optional[HealthChecker] = None


def set_global_vector_store_manager(vector_store_manager: VectorStoreManager) -> None:
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker(vector_store_manager=vector_store_manager)
    else:
        _health_checker.set_vector_store_manager(vector_store_manager)
    logger.info("Health checker initialized with shared VectorStoreManager")


def _get_health_checker() -> HealthChecker:
    global _health_checker
    if _health_checker is None:
        logger.warning("Health checker created without VectorStoreManager (info probes only)")
        _health_checker = HealthChecker()
    return _health_checker


async def get_health_status() -> Dict[str, Any]:
    return await _get_health_checker().get_comprehensive_health()


def get_liveness() -> Dict[str, Any]:
    return _get_health_checker().get_liveness()


async def get_readiness() -> Dict[str, Any]:
    return await _get_health_checker().get_readiness()
