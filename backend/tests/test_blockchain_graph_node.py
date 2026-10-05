"""Tests for the blockchain_lookup graph node and graph routing."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestBlockchainGraphRouting:
    """Verify the graph correctly routes blockchain_lookup intent."""

    def test_after_prechecks_routes_blockchain(self):
        """Conditional edge routes blockchain intent to blockchain_lookup node."""
        from backend.rag_graph.state import RAGState

        state: RAGState = {"intent": "blockchain_lookup", "matched_faq": "fees"}  # type: ignore[typeddict-item]

        from backend.rag_graph.graph import build_rag_graph

        dummy_node = AsyncMock(return_value={})
        nodes = {
            "sanitize_normalize": dummy_node,
            "safety_gate": dummy_node,
            "route": dummy_node,
            "prechecks": dummy_node,
            "semantic_cache": dummy_node,
            "decompose": dummy_node,
            "retrieve": dummy_node,
            "resolve_parents": dummy_node,
            "spend_limit": dummy_node,
            "generate": dummy_node,
            "blockchain_lookup": dummy_node,
        }
        graph = build_rag_graph(nodes)
        assert graph is not None

    def test_after_prechecks_still_routes_search(self):
        """Non-blockchain intent still goes to semantic_cache."""
        from backend.rag_graph.state import RAGState

        state: RAGState = {"intent": "search"}  # type: ignore[typeddict-item]
        assert state.get("intent") == "search"
        assert state.get("early_answer") is None


class TestBlockchainLookupNode:
    """Test the blockchain_lookup node function."""

    @pytest.fixture
    def mock_pipeline(self):
        pipeline = MagicMock()
        pipeline.get_redis_client = AsyncMock(return_value=None)
        return pipeline

    @pytest.mark.asyncio
    async def test_fee_lookup(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.blockchain_client import FeeData

        node = make_blockchain_lookup_node(mock_pipeline)

        mock_fees = FeeData(fastestFee=2, halfHourFee=1, hourFee=1, economyFee=1, minimumFee=1)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient:
            instance = AsyncMock()
            instance.get_recommended_fees = AsyncMock(return_value=mock_fees)
            MockClient.return_value = instance

            state = {
                "intent": "blockchain_lookup",
                "matched_faq": "fees",
                "sanitized_query": "What are current fees?",
                "metadata": {},
            }
            result = await node(state)

        assert result.get("early_answer") is not None
        assert "Fastest" in result["early_answer"]
        assert result.get("blockchain_data") is not None
        assert result.get("blockchain_lookup_type") == "fees"
        assert result.get("early_cache_type") == "blockchain_lookup"

    @pytest.mark.asyncio
    async def test_price_lookup(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.blockchain_client import PriceData

        node = make_blockchain_lookup_node(mock_pipeline)

        mock_price = PriceData(time=1700000000, USD=72.50, EUR=67.0, GBP=58.0)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient:
            instance = AsyncMock()
            instance.get_price = AsyncMock(return_value=mock_price)
            MockClient.return_value = instance

            state = {
                "intent": "blockchain_lookup",
                "matched_faq": "price",
                "sanitized_query": "What is the litecoin price?",
                "metadata": {},
            }
            result = await node(state)

        assert result.get("early_answer") is not None
        assert "$72.50" in result["early_answer"]
        assert result.get("blockchain_lookup_type") == "price"

    @pytest.mark.asyncio
    async def test_api_error_sets_error_message(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node

        node = make_blockchain_lookup_node(mock_pipeline)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient:
            instance = AsyncMock()
            instance.get_recommended_fees = AsyncMock(side_effect=Exception("API timeout"))
            MockClient.return_value = instance

            state = {
                "intent": "blockchain_lookup",
                "matched_faq": "fees",
                "sanitized_query": "fees",
                "metadata": {},
            }
            result = await node(state)

        assert result.get("early_answer") is not None
        assert "blockchain" in result["early_answer"].lower()
        assert result.get("early_cache_type") == "blockchain_lookup_error"

    @pytest.mark.asyncio
    async def test_mining_pools_lookup(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node

        node = make_blockchain_lookup_node(mock_pipeline)
        sample = {
            "pools": [
                {
                    "name": "Alpha",
                    "rank": 1,
                    "blockCount": 50,
                    "slug": "alpha",
                    "link": "",
                }
            ],
            "blockCount": 50,
            "lastEstimatedHashrate": 1e15,
        }

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient:
            instance = AsyncMock()
            instance.get_mining_pools = AsyncMock(return_value=sample)
            MockClient.return_value = instance

            state = {
                "intent": "blockchain_lookup",
                "matched_faq": "mining_pools",
                "sanitized_query": "List Litecoin mining pools",
                "metadata": {},
            }
            result = await node(state)

        assert result.get("blockchain_lookup_type") == "mining_pools"
        assert "Alpha" in result["early_answer"]
        assert result.get("early_cache_type") == "blockchain_lookup"

    @pytest.mark.asyncio
    async def test_unknown_entity_no_crash(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node

        node = make_blockchain_lookup_node(mock_pipeline)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient:
            MockClient.return_value = AsyncMock()

            state = {
                "intent": "blockchain_lookup",
                "matched_faq": "something_unknown",
                "sanitized_query": "???",
                "metadata": {},
            }
            result = await node(state)

        assert result.get("early_answer") is None
        assert result.get("error_message") is None


class TestMetricLookupBranch:
    """`metric:<id>` entities are served by litview.space via the same node."""

    @pytest.fixture
    def mock_pipeline(self):
        pipeline = MagicMock()
        pipeline.get_redis_client = AsyncMock(return_value=None)
        return pipeline

    def _state(self, entity="metric:mvrv", query="litecoin mvrv right now"):
        return {"intent": "blockchain_lookup", "matched_faq": entity, "sanitized_query": query, "metadata": {}}

    @pytest.mark.asyncio
    async def test_metric_ok_renders_card_and_narration(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.litview_client import MetricSnapshot, SeriesPoint

        snap = MetricSnapshot(
            series="price_close", index="day1", value=71.67, as_of=1791158400,
            points=[SeriesPoint(t=1791072000, v=70.19), SeriesPoint(t=1791158400, v=71.67)],
            changes_pct={7: 1.5, 30: 28.27}, stamp="2026-10-05T19:23:03Z",
            endpoint="/api/series/price_close/day1",
        )
        node = make_blockchain_lookup_node(mock_pipeline)
        with patch("backend.services.litview_client.LitviewClient") as MockClient:
            instance = AsyncMock()
            instance.get_metric_snapshot = AsyncMock(return_value=snap)
            MockClient.return_value = instance
            result = await node(self._state("metric:price_close", "daily close price"))

        assert result["blockchain_lookup_type"] == "metric"
        assert result["early_cache_type"] == "blockchain_lookup"
        card = result["blockchain_data"]
        assert card["status"] == "ok"
        assert card["metric_id"] == "price_close" and card["unit"] == "usd"
        assert card["value"] == 71.67 and card["value_formatted"] == "$71.67"
        assert card["points"] == [{"t": 1791072000, "v": 70.19}, {"t": 1791158400, "v": 71.67}]
        assert card["changes"] == {"7": 1.5, "30": 28.27}
        assert card["_provenance"]["source"] == "litview.space"
        assert card["_provenance"]["endpoint"] == "/api/series/price_close/day1"
        answer = result["early_answer"]
        assert "**Daily close price: $71.67**" in answer
        assert "+1.5%" in answer and "+28.3%" in answer
        assert "litview.space" in answer
        assert result["metadata"]["metric_status"] == "ok"
        instance.get_metric_snapshot.assert_awaited_once_with("price_close", "day1", points=30, change_windows=(7, 30))

    @pytest.mark.asyncio
    async def test_metric_not_computed_says_so_without_guessing(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.litview_client import MetricNotComputed

        node = make_blockchain_lookup_node(mock_pipeline)
        with patch("backend.services.litview_client.LitviewClient") as MockClient:
            instance = AsyncMock()
            instance.get_metric_snapshot = AsyncMock(
                side_effect=MetricNotComputed("mvrv", "day1", computed_height=2520000,
                                              computed_at="2023-08-02", tip_height=3189505)
            )
            MockClient.return_value = instance
            result = await node(self._state())

        card = result["blockchain_data"]
        assert card["status"] == "not_computed"
        assert card["value"] is None and card["points"] == []
        assert card["computed_height"] == 2520000 and card["tip_height"] == 3189505
        answer = result["early_answer"]
        assert "not computed yet" in answer
        assert "2,520,000" in answer and "3,189,505" in answer and "2023-08-02" in answer
        assert "won't estimate" in answer
        # An honest answer, not a tool error — but still never cached (early_cache_type is excluded upstream)
        assert result["early_cache_type"] == "blockchain_lookup"
        assert result["metadata"]["metric_status"] == "not_computed"

    @pytest.mark.asyncio
    async def test_metric_litview_down_is_tool_unavailable(self, mock_pipeline):
        import httpx
        from backend.rag_graph.nodes.blockchain_lookup import LITVIEW_UNAVAILABLE_MESSAGE, make_blockchain_lookup_node

        node = make_blockchain_lookup_node(mock_pipeline)
        with patch("backend.services.litview_client.LitviewClient") as MockClient:
            instance = AsyncMock()
            instance.get_metric_snapshot = AsyncMock(side_effect=httpx.ConnectError("down"))
            MockClient.return_value = instance
            result = await node(self._state())

        assert result["early_answer"] == LITVIEW_UNAVAILABLE_MESSAGE
        assert result["early_cache_type"] == "blockchain_lookup_error"
        assert result["metadata"]["tool_unavailable"] == "litview"
        assert result["metadata"]["intent"] == "blockchain_lookup"

    @pytest.mark.asyncio
    async def test_metric_5xx_is_tool_unavailable_too(self, mock_pipeline):
        import httpx
        from backend.rag_graph.nodes.blockchain_lookup import LITVIEW_UNAVAILABLE_MESSAGE, make_blockchain_lookup_node

        req = httpx.Request("GET", "https://litview.space/api/server/sync")
        err = httpx.HTTPStatusError("504", request=req, response=httpx.Response(504, request=req))
        node = make_blockchain_lookup_node(mock_pipeline)
        with patch("backend.services.litview_client.LitviewClient") as MockClient:
            instance = AsyncMock()
            instance.get_metric_snapshot = AsyncMock(side_effect=err)
            MockClient.return_value = instance
            result = await node(self._state())
        assert result["early_answer"] == LITVIEW_UNAVAILABLE_MESSAGE

    @pytest.mark.asyncio
    async def test_metric_series_not_found_is_graceful(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.litview_client import LitviewSeriesNotFound

        node = make_blockchain_lookup_node(mock_pipeline)
        with patch("backend.services.litview_client.LitviewClient") as MockClient:
            instance = AsyncMock()
            instance.get_metric_snapshot = AsyncMock(side_effect=LitviewSeriesNotFound("mvrv"))
            MockClient.return_value = instance
            result = await node(self._state())
        assert "did not recognise the series `mvrv`" in result["early_answer"]
        assert result["early_cache_type"] == "blockchain_lookup_error"

    @pytest.mark.asyncio
    async def test_unknown_metric_id(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node

        node = make_blockchain_lookup_node(mock_pipeline)
        result = await node(self._state("metric:does_not_exist", "x"))
        assert "Unknown metric" in result["early_answer"]
        assert result["early_cache_type"] == "blockchain_lookup_error"
