"""Tests for the lrk_lookup graph node."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_lrk_lookup_sets_chart_spec():
    from backend.rag_graph.nodes.lrk_lookup import make_lrk_lookup_node

    artifact = {
        "type": "chart",
        "chart": {
            "title": "Realized Price",
            "unit": "usd",
            "view": "line",
            "scale": "linear",
            "series": [{"path": "realized-price", "label": "Realized Price", "color": "orange"}],
        },
    }
    pipeline = MagicMock()
    node = make_lrk_lookup_node(pipeline)

    with patch(
        "backend.services.lrk_chart.plan_lrk_chart",
        new=AsyncMock(return_value=artifact),
    ):
        result = await node(
            {
                "intent": "lrk_metric",
                "sanitized_query": "chart realized price",
                "metadata": {},
            }
        )

    assert result["chart_spec"] == artifact
    assert result.get("early_answer")
    assert "Realized Price" in result["early_answer"]
    assert result["early_cache_type"] == "lrk_lookup"


@pytest.mark.asyncio
async def test_lrk_lookup_empty_search():
    from backend.rag_graph.nodes.lrk_lookup import make_lrk_lookup_node

    node = make_lrk_lookup_node(MagicMock())
    with patch(
        "backend.services.lrk_chart.plan_lrk_chart",
        new=AsyncMock(return_value=None),
    ):
        result = await node(
            {
                "intent": "lrk_metric",
                "sanitized_query": "chart florbnitz",
                "metadata": {},
            }
        )

    assert result.get("chart_spec") is None
    assert result["early_cache_type"] == "lrk_lookup_empty"
    assert "could not find" in result["early_answer"].lower()
