"""
LRK metric / chart node.

Searches litview series, asks Gemini for a validated chart-spec, and sets
early_answer + chart_spec so the stream can emit both narration and a chart.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from ..state import RAGState

logger = logging.getLogger(__name__)


def make_lrk_lookup_node(pipeline: Any):
    async def lrk_lookup(state: RAGState) -> RAGState:
        from backend.services.lrk_chart import metric_search_query, plan_lrk_chart
        from backend.services.lrk_client import LrkClient

        query = state.get("sanitized_query") or state.get("raw_query") or ""
        metadata: Dict[str, Any] = state.get("metadata") or {}
        start = time.time()
        client = LrkClient()

        try:
            artifact = await plan_lrk_chart(pipeline, query, client=client)
            if artifact is None:
                metric = metric_search_query(query) or query
                state["early_answer"] = (
                    f"I could not find a Litecoin Research Kit series matching **{metric}**. "
                    "Try a metric name such as realized price, market cap, or MVRV."
                )
                state["early_sources"] = []
                state["early_cache_type"] = "lrk_lookup_empty"
                metadata.update(
                    {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "cache_hit": False,
                        "cache_type": "lrk_lookup_empty",
                        "intent": "lrk_metric",
                        "lrk_lookup_duration": time.time() - start,
                    }
                )
                state["metadata"] = metadata
                return state

            title = artifact.get("chart", {}).get("title") or "Litecoin series"
            paths = [
                item.get("path")
                for item in artifact.get("chart", {}).get("series", [])
                if item.get("path")
            ]
            listed = ", ".join(f"`{path}`" for path in paths) or "the selected series"
            state["chart_spec"] = artifact
            state["early_answer"] = (
                f"Here is a chart of **{title}** from Litecoin Research Kit "
                f"({listed})."
            )
            state["early_sources"] = []
            state["early_cache_type"] = "lrk_lookup"
            metadata.update(
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "cache_hit": False,
                    "cache_type": "lrk_lookup",
                    "intent": "lrk_metric",
                    "lrk_lookup_duration": time.time() - start,
                }
            )
        except Exception as exc:
            logger.error("LRK lookup failed: %s", exc, exc_info=True)
            state["early_answer"] = (
                "Unable to fetch Litecoin Research Kit metrics right now. "
                "Please try again in a moment."
            )
            state["early_sources"] = []
            state["early_cache_type"] = "lrk_lookup_error"
            metadata.update(
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "cache_hit": False,
                    "cache_type": "lrk_lookup_error",
                    "intent": "lrk_metric",
                }
            )
        finally:
            await client.close()

        state["metadata"] = metadata
        return state

    return lrk_lookup
