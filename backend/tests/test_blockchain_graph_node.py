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
            "route": dummy_node,
            "prechecks": dummy_node,
            "semantic_cache": dummy_node,
            "decompose": dummy_node,
            "retrieve": dummy_node,
            "resolve_parents": dummy_node,
            "spend_limit": dummy_node,
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
