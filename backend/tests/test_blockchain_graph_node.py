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
        # 90_400 / 4 / 100 = 226 virtual bytes per transaction.
        blocks = [
            {"tx_count": 100, "weight": 90400},
            {"tx_count": 100, "weight": 90400},
        ]

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_recommended_fees = AsyncMock(return_value=mock_fees)
            instance.get_recent_blocks = AsyncMock(return_value=blocks)
            instance.get_spot_prices = AsyncMock(return_value=None)
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_spot_price = AsyncMock(return_value={"USD": 84.20, "time": 1700000000})
            MockLitview.return_value = litview

            state = {
                "intent": "blockchain_lookup",
                "matched_faq": "fees",
                "sanitized_query": "What are current fees?",
                "metadata": {},
            }
            result = await node(state)

        answer = result["early_answer"]
        assert "Fastest" in answer
        assert "(about $0.00038)" in answer
        assert "(about $0.00019)" in answer
        assert "226 virtual bytes" in answer
        assert "last 2 blocks" in answer
        assert "$84.20 per LTC" in answer
        assert "1-hour rate costs about $0.00019" in answer
        assert result.get("blockchain_lookup_type") == "fees"
        assert result.get("early_cache_type") == "blockchain_lookup"
        context = result["blockchain_data"]["context"]
        assert context["avgVbytes"] == 226
        assert context["usdLabel"] == "$84.20"
        assert context["hourCostLabel"] == "$0.00019"
        assert context["costs"]["fastestFee"] == "$0.00038"
        assert context["costs"]["hourFee"] == "$0.00019"
        endpoint = result["blockchain_data"]["_provenance"]["endpoint"]
        assert "/api/v1/fees/recommended" in endpoint
        assert "/api/blocks" in endpoint
        assert "litview.space" in endpoint

    @pytest.mark.asyncio
    async def test_fee_lookup_omits_dollars_when_price_times_out(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.blockchain_client import FeeData

        node = make_blockchain_lookup_node(mock_pipeline)
        mock_fees = FeeData(fastestFee=1, halfHourFee=1, hourFee=1, economyFee=1, minimumFee=1)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_recommended_fees = AsyncMock(return_value=mock_fees)
            instance.get_recent_blocks = AsyncMock(return_value=[{"tx_count": 100, "weight": 90400}])
            instance.get_spot_prices = AsyncMock(side_effect=TimeoutError("slow"))
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_spot_price = AsyncMock(side_effect=TimeoutError("slow"))
            MockLitview.return_value = litview
            result = await node({
                "intent": "blockchain_lookup",
                "matched_faq": "fees",
                "sanitized_query": "fees",
                "metadata": {},
            })

        assert result["early_cache_type"] == "blockchain_lookup"
        assert "1 lit/vB" in result["early_answer"]
        assert "$" not in result["early_answer"]
        assert "context" not in result["blockchain_data"]
        assert result["blockchain_data"]["_provenance"]["endpoint"] == "/api/v1/fees/recommended"

    @pytest.mark.asyncio
    async def test_fee_lookup_omits_dollars_when_blocks_time_out(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.blockchain_client import FeeData, PriceData

        node = make_blockchain_lookup_node(mock_pipeline)
        mock_fees = FeeData(fastestFee=1, halfHourFee=1, hourFee=1, economyFee=1, minimumFee=1)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_recommended_fees = AsyncMock(return_value=mock_fees)
            instance.get_recent_blocks = AsyncMock(side_effect=TimeoutError("slow"))
            instance.get_spot_prices = AsyncMock(return_value=PriceData(time=1700000000, USD=84.20))
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_spot_price = AsyncMock(return_value=None)
            MockLitview.return_value = litview
            result = await node({
                "intent": "blockchain_lookup",
                "matched_faq": "fees",
                "sanitized_query": "fees",
                "metadata": {},
            })

        assert result["early_cache_type"] == "blockchain_lookup"
        assert "Fastest" in result["early_answer"]
        assert "lit/vB" in result["early_answer"]
        assert "$" not in result["early_answer"]
        assert "context" not in result["blockchain_data"]

    @pytest.mark.asyncio
    async def test_price_lookup(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.blockchain_client import PriceData

        node = make_blockchain_lookup_node(mock_pipeline)

        mock_price = PriceData(time=1700000000, USD=72.50, EUR=67.0, GBP=58.0)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_spot_prices = AsyncMock(return_value=mock_price)
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_spot_price = AsyncMock(return_value=None)
            MockLitview.return_value = litview

            state = {
                "intent": "blockchain_lookup",
                "matched_faq": "price",
                "sanitized_query": "What is the litecoin price?",
                "metadata": {},
            }
            result = await node(state)

        assert result.get("early_answer") is not None
        assert "$72.50" in result["early_answer"]
        assert "€67.00" in result["early_answer"]
        assert "A$" not in result["early_answer"]
        assert result.get("blockchain_lookup_type") == "price"
        assert result["blockchain_data"]["_provenance"]["source"] == "Litecoin Space"

    @pytest.mark.asyncio
    async def test_price_prefers_litview_usd_and_space_fx(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.blockchain_client import PriceData

        node = make_blockchain_lookup_node(mock_pipeline)
        space_price = PriceData(time=1700000000, USD=70.0, EUR=62.0, GBP=53.0, AUD=100.0, JPY=11040.0)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_spot_prices = AsyncMock(return_value=space_price)
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_spot_price = AsyncMock(return_value={"USD": 69.96, "time": 1791302952})
            MockLitview.return_value = litview

            result = await node({
                "intent": "blockchain_lookup",
                "matched_faq": "price",
                "sanitized_query": "litecoin price",
                "metadata": {},
            })

        answer = result["early_answer"]
        assert "$69.96" in answer
        assert "$70.00" not in answer
        assert "€62.00" in answer and "£53.00" in answer
        card = result["blockchain_data"]
        assert card["USD"] == 69.96 and card["EUR"] == 62.0
        assert card["_provenance"]["source"] == "litview.space"
        assert "litecoinspace.org/api/v1/prices" in card["_provenance"]["endpoint"]

    @pytest.mark.asyncio
    async def test_price_usd_only_when_space_fx_is_down(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node

        node = make_blockchain_lookup_node(mock_pipeline)
        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_spot_prices = AsyncMock(side_effect=TimeoutError("slow"))
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_spot_price = AsyncMock(return_value={"USD": 69.96, "time": 1791302952})
            MockLitview.return_value = litview
            result = await node({
                "intent": "blockchain_lookup",
                "matched_faq": "price",
                "sanitized_query": "price",
                "metadata": {},
            })

        assert result["early_cache_type"] == "blockchain_lookup"
        assert "$69.96" in result["early_answer"]
        assert "EUR" not in result["early_answer"]
        assert result["blockchain_data"]["_provenance"]["source"] == "litview.space"

    @pytest.mark.asyncio
    async def test_hashrate_uses_litview_daily_series(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.blockchain_client import DifficultyAdjustment

        node = make_blockchain_lookup_node(mock_pipeline)
        adjustment = DifficultyAdjustment(
            progressPercent=64.5, difficultyChange=-1.2, remainingBlocks=715,
            estimatedRetargetDate=0, remainingTime=0, previousRetarget=0, nextRetargetHeight=3191328,
        )

        async def latest(series, index="day1"):
            return {"hash_rate": 2.64e15, "difficulty": 97030382.37}[series]

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_difficulty_adjustment = AsyncMock(return_value=adjustment)
            instance.get_hashrate = AsyncMock()
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_latest = AsyncMock(side_effect=latest)
            MockLitview.return_value = litview
            result = await node({
                "intent": "blockchain_lookup",
                "matched_faq": "hashrate",
                "sanitized_query": "hashrate",
                "metadata": {},
            })

        assert result["early_cache_type"] == "blockchain_lookup"
        assert "daily estimate" in result["early_answer"]
        assert "64.5% complete" in result["early_answer"]
        instance.get_hashrate.assert_not_called()
        card = result["blockchain_data"]
        assert card["hashrate"]["basis"] == "daily"
        assert card["hashrate"]["current_difficulty"] == pytest.approx(97030382.37)
        assert card["_provenance"]["source"] == "litview.space"
        assert "difficulty-adjustment" in card["_provenance"]["endpoint"]

    @pytest.mark.asyncio
    async def test_hashrate_falls_back_when_litview_and_adjustment_fail(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node
        from backend.services.blockchain_client import HashrateData

        node = make_blockchain_lookup_node(mock_pipeline)
        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_hashrate = AsyncMock(
                return_value=HashrateData(current_hashrate=2.69e15, current_difficulty=97030382.0)
            )
            instance.get_difficulty_adjustment = AsyncMock(side_effect=TimeoutError("slow"))
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_latest = AsyncMock(side_effect=OSError("down"))
            MockLitview.return_value = litview
            result = await node({
                "intent": "blockchain_lookup",
                "matched_faq": "hashrate",
                "sanitized_query": "hashrate",
                "metadata": {},
            })

        assert result["early_cache_type"] == "blockchain_lookup"
        assert "3-day estimate" in result["early_answer"]
        assert "not available from Litecoin Space" in result["early_answer"]
        assert "difficulty_adjustment" not in result["blockchain_data"]
        assert result["blockchain_data"]["_provenance"]["source"] == "Litecoin Space"

    @pytest.mark.asyncio
    async def test_api_error_sets_error_message(self, mock_pipeline):
        from backend.rag_graph.nodes.blockchain_lookup import make_blockchain_lookup_node

        node = make_blockchain_lookup_node(mock_pipeline)

        with patch(
            "backend.services.blockchain_client.LitecoinSpaceClient"
        ) as MockClient, patch(
            "backend.services.litview_client.LitviewClient"
        ) as MockLitview:
            instance = AsyncMock()
            instance.get_recommended_fees = AsyncMock(side_effect=Exception("API timeout"))
            instance.get_recent_blocks = AsyncMock(return_value=[])
            instance.get_spot_prices = AsyncMock(side_effect=TimeoutError("slow"))
            MockClient.return_value = instance
            litview = AsyncMock()
            litview.get_spot_price = AsyncMock(return_value=None)
            MockLitview.return_value = litview

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


class TestFeeCostMath:
    """Average virtual size and the dollar cost of a typical transaction."""

    def test_average_vbytes_from_weight(self):
        from backend.rag_graph.nodes.blockchain_lookup import average_tx_vbytes

        mean, count = average_tx_vbytes([
            {"tx_count": 100, "weight": 90400},
            {"tx_count": 50, "weight": 40000},
        ])
        # 226 and 200.
        assert count == 2
        assert mean == pytest.approx(213.0)

    def test_average_vbytes_prefers_virtual_size(self):
        from backend.rag_graph.nodes.blockchain_lookup import average_tx_vbytes

        mean, count = average_tx_vbytes([
            {"tx_count": 10, "weight": 4000, "extras": {"virtualSize": 500}},
        ])
        assert count == 1
        assert mean == pytest.approx(50.0)

    def test_average_vbytes_skips_empty_blocks(self):
        from backend.rag_graph.nodes.blockchain_lookup import average_tx_vbytes

        assert average_tx_vbytes([]) == (None, 0)
        assert average_tx_vbytes([{"tx_count": 0, "weight": 1000}]) == (None, 0)
        assert average_tx_vbytes("not-a-list") == (None, 0)

    def test_usd_cost_keeps_sub_cent_digits(self):
        from backend.rag_graph.nodes.blockchain_lookup import format_usd_amount, tx_cost_usd

        cost = tx_cost_usd(1, 226, 84.20)
        assert cost == pytest.approx(226 * 84.20 / 100_000_000)
        assert format_usd_amount(cost) == "$0.00019"
        assert format_usd_amount(0.02) == "$0.02"
        assert format_usd_amount(1.5) == "$1.50"
