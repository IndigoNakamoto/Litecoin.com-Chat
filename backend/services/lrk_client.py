"""
Litecoin Research Kit (litview) HTTP client.

Read-only access to series search and series data. Every chart series path
must be resolved against search results — never trust model-emitted ids raw.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

LRK_API_URL = os.getenv("LRK_API_URL", "https://litview.space").rstrip("/")

_SERIES_PREFIX_RE = re.compile(r"^(brk\.series\.|series\.)")


def normalize_series_path(name: str) -> str:
    """Strip catalog prefixes and surrounding whitespace."""
    return _SERIES_PREFIX_RE.sub("", (name or "").strip())


class LrkClient:
    """Async client for litview / LRK `/api/series/*`."""

    def __init__(self, base_url: Optional[str] = None, redis_client=None):
        self._base = (base_url or LRK_API_URL).rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self._base,
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._redis = redis_client

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        from backend.services.circuit_breaker import CircuitOpen, lrk_breaker

        async def _do() -> httpx.Response:
            return await self._request_inner(path, params)

        try:
            return await lrk_breaker.call(_do)
        except CircuitOpen:
            raise httpx.ConnectError(f"LRK circuit open ({path})")

    async def _request_inner(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp

    async def search_series(self, q: str, limit: int = 20) -> List[str]:
        """GET /api/series/search?q=&limit= — list of series name strings."""
        query = (q or "").strip()
        if not query:
            return []
        resp = await self._request("/api/series/search", {"q": query, "limit": limit})
        data = resp.json()
        if not isinstance(data, list):
            logger.warning("LRK search returned non-list: %s", type(data).__name__)
            return []
        names: List[str] = []
        for item in data:
            if isinstance(item, str) and item.strip():
                names.append(normalize_series_path(item))
        return names

    async def get_series_info(self, name: str) -> Dict[str, Any]:
        """GET /api/series/{name} — indexes and value type."""
        path = normalize_series_path(name)
        resp = await self._request(f"/api/series/{path}")
        data = resp.json()
        return data if isinstance(data, dict) else {}

    async def get_series(
        self,
        name: str,
        index: str = "date",
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Any:
        """GET /api/series/{name}/{index}."""
        path = normalize_series_path(name)
        params: Dict[str, Any] = {}
        if start is not None:
            params["from"] = start
        if end is not None:
            params["to"] = end
        if limit is not None:
            params["limit"] = limit
        resp = await self._request(f"/api/series/{path}/{index}", params or None)
        return resp.json()

    async def get_series_latest(self, name: str, index: str = "date") -> Any:
        """GET /api/series/{name}/{index}/latest."""
        path = normalize_series_path(name)
        resp = await self._request(f"/api/series/{path}/{index}/latest")
        return resp.json()

    def validate_series(self, name: str, candidates: List[str]) -> Optional[str]:
        """Return the canonical series name if it appears in search hits."""
        normalized = normalize_series_path(name)
        if not normalized or not candidates:
            return None
        allowed = {normalize_series_path(item) for item in candidates}
        if normalized in allowed:
            return normalized
        return None

    async def resolve_series(self, name: str, hint: Optional[str] = None) -> Optional[str]:
        """Search for `name` (and optional hint) and accept only an exact hit."""
        normalized = normalize_series_path(name)
        queries = [normalized]
        if hint and hint.strip() and hint.strip() != normalized:
            queries.append(hint.strip())
        seen: List[str] = []
        for query in queries:
            hits = await self.search_series(query)
            for hit in hits:
                if hit not in seen:
                    seen.append(hit)
            resolved = self.validate_series(normalized, hits)
            if resolved:
                return resolved
        return None
