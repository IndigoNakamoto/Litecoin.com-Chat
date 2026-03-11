from __future__ import annotations

import os
import re
from typing import Any, List, Tuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.utils.litecoin_vocabulary import expand_ltc_entities

from ..state import RAGState

COMPLEX_QUERY_TOKEN_THRESHOLD = int(os.getenv("COMPLEX_QUERY_TOKEN_THRESHOLD", "18"))
COMPLEX_QUERY_MULTI_CLAUSE_THRESHOLD = int(os.getenv("COMPLEX_QUERY_MULTI_CLAUSE_THRESHOLD", "2"))
_COMPLEX_SIGNAL_TERMS = (
    "compare",
    "tradeoff",
    "pros and cons",
    "in depth",
    "step by step",
    "analyze",
    "evaluate",
    "explain why",
    "architecture",
    "security implications",
    "economics",
)


def _classify_query_complexity(query_text: str) -> str:
    """Fast deterministic complexity routing for response profile selection."""
    normalized = (query_text or "").strip().lower()
    if not normalized:
        return "simple"
    tokens = re.findall(r"[a-z0-9']+", normalized)
    clause_markers = len(re.findall(r"\b(and|or|vs|versus|while|whereas)\b|[,:;]", normalized))
    has_complex_term = any(term in normalized for term in _COMPLEX_SIGNAL_TERMS)
    if (
        len(tokens) >= COMPLEX_QUERY_TOKEN_THRESHOLD
        or clause_markers >= COMPLEX_QUERY_MULTI_CLAUSE_THRESHOLD
        or has_complex_term
    ):
        return "complex"
    return "simple"


def make_route_node(pipeline: Any):
    async def route(state: RAGState) -> RAGState:
        normalized_query = state.get("normalized_query") or state.get("sanitized_query") or state.get("raw_query") or ""
        truncated_history: List[Tuple[str, str]] = state.get("truncated_history_pairs") or []
        metadata = state.get("metadata") or {}

        # Default: no history dependency
        effective_query = normalized_query
        effective_history_pairs: List[Tuple[str, str]] = []
        is_dependent = False
        complexity_route = _classify_query_complexity(normalized_query)

        # No history => no routing work
        if not truncated_history:
            state.update(
                {
                    "effective_query": effective_query,
                    "effective_history_pairs": [],
                    "is_dependent": False,
                    "converted_history_messages": [],
                    "complexity_route": complexity_route,
                }
            )
            metadata["complexity_route"] = complexity_route
            state["metadata"] = metadata
            return state

        # Deterministic pronoun anchoring (anti-topic-drift), then entity expansion (topic reinforcement)
        router_input = (
            pipeline._anchor_pronouns_to_last_entity(normalized_query, truncated_history)  # type: ignore[attr-defined]
            if hasattr(pipeline, "_anchor_pronouns_to_last_entity")
            else normalized_query
        )
        router_input = expand_ltc_entities(router_input)

        # Fast path: obvious dependency via tokens/prefixes if pipeline exposes the lists; otherwise fall back to router.
        tokens = re.findall(r"[a-z0-9']+", router_input.lower())
        strong_tokens = getattr(pipeline, "strong_ambiguous_tokens", None)
        strong_prefixes = getattr(pipeline, "strong_prefixes", None)
        has_obvious_pronouns = bool(strong_tokens) and any(t in strong_tokens for t in tokens)
        has_obvious_prefix = bool(strong_prefixes) and any(router_input.lower().startswith(p) for p in strong_prefixes)

        # Convert full truncated history to messages for router
        converted_full_history: List[BaseMessage] = []
        for human_msg, ai_msg in truncated_history:
            converted_full_history.append(HumanMessage(content=human_msg))
            if ai_msg:
                converted_full_history.append(AIMessage(content=ai_msg))

        if has_obvious_pronouns or has_obvious_prefix:
            is_dependent = True
            effective_history_pairs = truncated_history
            if hasattr(pipeline, "_semantic_history_check"):
                effective_query, _ = await pipeline._semantic_history_check(router_input, converted_full_history)  # type: ignore[attr-defined]
            else:
                effective_query = router_input
        else:
            if hasattr(pipeline, "_semantic_history_check"):
                effective_query, is_dependent = await pipeline._semantic_history_check(router_input, converted_full_history)  # type: ignore[attr-defined]
            else:
                effective_query, is_dependent = router_input, False

            effective_history_pairs = truncated_history if is_dependent else []

        # Convert effective history to messages for downstream generation
        converted_effective_history: List[BaseMessage] = []
        for human_msg, ai_msg in effective_history_pairs:
            converted_effective_history.append(HumanMessage(content=human_msg))
            if ai_msg:
                converted_effective_history.append(AIMessage(content=ai_msg))

        state.update(
            {
                "effective_query": effective_query,
                "is_dependent": is_dependent,
                "effective_history_pairs": effective_history_pairs,
                "converted_history_messages": converted_effective_history,
                "complexity_route": complexity_route,
            }
        )
        metadata["complexity_route"] = complexity_route
        state["metadata"] = metadata
        return state

    return route


