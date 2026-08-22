"""Tests for the Litecoin Research Kit HTTP client."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.services.lrk_client import LrkClient, normalize_series_path


class TestNormalizeSeriesPath:
    def test_strips_prefixes(self):
        assert normalize_series_path("brk.series.realized-price") == "realized-price"
        assert normalize_series_path("series.market-cap") == "market-cap"
        assert normalize_series_path("  realized-price  ") == "realized-price"


class TestLrkClient:
    @pytest.fixture
    def mock_http(self):
        http = AsyncMock()
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        http.get = AsyncMock(return_value=response)
        return http, response

    @pytest.fixture
    def client(self, mock_http):
        http, _ = mock_http
        instance = LrkClient(base_url="https://litview.space")
        instance._http = http
        return instance

    @pytest.mark.asyncio
    async def test_search_series(self, client, mock_http):
        _, response = mock_http
        response.json.return_value = ["realized-price", "series.market-cap"]
        hits = await client.search_series("realized", limit=10)
        assert hits == ["realized-price", "market-cap"]
        mock_http[0].get.assert_called_once()
        args, kwargs = mock_http[0].get.call_args
        assert args[0] == "/api/series/search"
        assert kwargs["params"]["q"] == "realized"
        assert kwargs["params"]["limit"] == 10

    @pytest.mark.asyncio
    async def test_search_empty_query(self, client, mock_http):
        assert await client.search_series("  ") == []
        mock_http[0].get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_series_latest(self, client, mock_http):
        _, response = mock_http
        response.json.return_value = 72.5
        value = await client.get_series_latest("realized-price", index="date")
        assert value == 72.5
        mock_http[0].get.assert_called_once_with(
            "/api/series/realized-price/date/latest", params=None
        )

    def test_validate_series_accepts_hit(self, client):
        assert client.validate_series("brk.series.realized-price", ["realized-price"]) == (
            "realized-price"
        )

    def test_validate_series_rejects_unknown(self, client):
        assert client.validate_series("not-a-metric", ["realized-price"]) is None

    @pytest.mark.asyncio
    async def test_resolve_series_requires_search_hit(self, client, mock_http):
        _, response = mock_http
        response.json.return_value = ["realized-price", "realized-cap"]
        assert await client.resolve_series("realized-price") == "realized-price"
        response.json.return_value = ["market-cap"]
        assert await client.resolve_series("realized-price") is None

    @pytest.mark.asyncio
    async def test_circuit_open_raises_connect(self, client, monkeypatch):
        from backend.services.circuit_breaker import CircuitOpen

        async def boom(_factory):
            raise CircuitOpen("lrk circuit open")

        monkeypatch.setattr("backend.services.circuit_breaker.lrk_breaker.call", boom)
        with pytest.raises(httpx.ConnectError):
            await client.search_series("price")
