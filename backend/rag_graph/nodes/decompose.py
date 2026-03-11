from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

from ..state import RAGState

USE_QUERY_DECOMPOSITION = os.getenv("USE_QUERY_DECOMPOSITION", "true").lower() == "true"

_COMPOUND_PATTERN = re.compile(
    r"""
    \b(?:and|or)\b              # explicit conjunctions
    |,\s*(?:and\s+)?            # comma-separated lists ("RBF, Child Key", "RBF, and Child Key")
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SYSTEM_PROMPT = (
    "You split compound user questions into separate search queries for a Litecoin knowledge base.\n"
    "If the question asks about multiple distinct topics, return one query per line.\n"
    "If it asks about one topic (even if it mentions related sub-concepts), return it as-is.\n"
    "Return ONLY the queries, no numbering, bullets, or extra text."
)


def make_decompose_node(pipeline: Any):
    async def decompose(state: RAGState) -> RAGState:
        """
        Query decomposition node.

        Detects compound queries (e.g. "Does Litecoin support RBF and Child Keys?")
        and splits them into separate retrieval sub-queries so each topic gets
        its own embedding and BM25 lookup.
        """
        metadata: Dict[str, Any] = state.get("metadata") or {}
        logger = logging.getLogger(__name__)
        complexity_route = str(state.get("complexity_route") or "simple").lower()

        retrieval_query = (
            state.get("retrieval_query")
            or state.get("rewritten_query")
            or state.get("effective_query")
            or state.get("sanitized_query")
            or ""
        )

        if state.get("early_answer") is not None or not retrieval_query:
            state["retrieval_queries"] = [retrieval_query] if retrieval_query else []
            state["metadata"] = metadata
            return state

        if not USE_QUERY_DECOMPOSITION:
            state["retrieval_queries"] = [retrieval_query]
            state["metadata"] = metadata
            return state

        if not _COMPOUND_PATTERN.search(retrieval_query):
            logger.debug("Decompose: no compound pattern detected, using single query")
            state["retrieval_queries"] = [retrieval_query]
            state["metadata"] = metadata
            return state

        llm = getattr(pipeline, "llm", None)
        if llm is None:
            logger.debug("Decompose: no LLM available, using single query")
            state["retrieval_queries"] = [retrieval_query]
            state["metadata"] = metadata
            return state

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            result = await llm.ainvoke([
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=retrieval_query),
            ])
            raw = getattr(result, "content", None) or str(result)

            sub_queries = [
                line.strip()
                for line in raw.strip().splitlines()
                if line.strip() and len(line.strip()) > 5
            ]

            if len(sub_queries) > 1:
                max_sub_queries = 6 if complexity_route == "complex" else 5
                sub_queries = sub_queries[:max_sub_queries]
                logger.info(
                    "Decompose: split '%s' into %d sub-queries: %s",
                    retrieval_query,
                    len(sub_queries),
                    sub_queries,
                )
                metadata["query_decomposed"] = True
                metadata["sub_queries"] = sub_queries
                metadata["complexity_route"] = complexity_route
                state["retrieval_queries"] = sub_queries
            else:
                logger.debug("Decompose: LLM returned single query, no split needed")
                state["retrieval_queries"] = [retrieval_query]

        except Exception as e:
            logger.warning("Decompose: LLM call failed, using single query: %s", e)
            state["retrieval_queries"] = [retrieval_query]

        state["metadata"] = metadata
        return state

    return decompose
