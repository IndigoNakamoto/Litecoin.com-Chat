from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.documents import Document

from ..state import RAGState


def make_semantic_cache_node(pipeline: Any):
    async def semantic_cache(state: RAGState) -> RAGState:
        """
        Semantic cache check (Redis vector cache or legacy semantic cache).

        In the skeleton, this is a no-op unless the pipeline exposes the needed objects.
        """
        metadata: Dict[str, Any] = state.get("metadata") or {}

        # If a previous node already produced an early answer, do nothing.
        if state.get("early_answer") is not None:
            state["metadata"] = metadata
            return state

        logger = logging.getLogger(__name__)

        rewritten_query = state.get("rewritten_query_for_cache") or state.get("rewritten_query") or ""

        # === 1) Embedding generation (Infinity) ===
        query_vector = None
        query_sparse = None

        if getattr(pipeline, "use_redis_cache", False) or getattr(pipeline, "use_infinity_embeddings", False):
            infinity = pipeline.get_infinity_embeddings() if hasattr(pipeline, "get_infinity_embeddings") else None
            if infinity:
                try:
                    query_vector, query_sparse = await infinity.embed_query(rewritten_query)
                    # Validate query vector dimension (best-effort)
                    if query_vector is not None and hasattr(infinity, "dimension"):
                        actual_dim = len(query_vector)
                        expected_dim = getattr(infinity, "dimension", actual_dim)
                        if expected_dim and actual_dim != expected_dim:
                            logger.error(
                                "Query vector dimension mismatch: got %s, expected %s (query=%r)",
                                actual_dim,
                                expected_dim,
                                rewritten_query[:80],
                            )
                except Exception as e:
                    logger.warning("Infinity embed_query failed: %s", e, exc_info=True)

        state["query_vector"] = query_vector
        state["query_sparse"] = query_sparse

        # === 2) Redis vector cache (unified semantic cache) ===
        if getattr(pipeline, "use_redis_cache", False) and query_vector:
            redis_cache = pipeline.get_redis_vector_cache() if hasattr(pipeline, "get_redis_vector_cache") else None
            if redis_cache:
                try:
                    cached_is_grounded = False
                    if hasattr(redis_cache, "get_entry"):
                        entry = await redis_cache.get_entry(query_vector)
                        redis_result = (entry.response, entry.sources) if entry else None
                        cached_is_grounded = bool(getattr(entry, "is_grounded", False)) if entry else False
                    else:
                        redis_result = await redis_cache.get(query_vector)
                    if redis_result:
                        answer, sources_data = redis_result
                        cached_sources = []
                        for src in sources_data:
                            if isinstance(src, dict):
                                cached_sources.append(
                                    Document(
                                        page_content=src.get("page_content", ""),
                                        metadata=src.get("metadata", {}),
                                    )
                                )
                            elif isinstance(src, Document):
                                cached_sources.append(src)

                        state.update(
                            {
                                "early_answer": answer,
                                "early_sources": cached_sources,
                                "early_cache_type": "redis_vector",
                            }
                        )
                        metadata.update(
                            {
                                "input_tokens": 0,
                                "output_tokens": 0,
                                "cost_usd": 0.0,
                                "cache_hit": True,
                                "cache_type": "redis_vector",
                                "rewritten_query": rewritten_query if rewritten_query else None,
                                # Replay the provenance flag the answer was stored with so a
                                # web-supplemented answer is still labelled as such on a hit.
                                "is_grounded": cached_is_grounded,
                            }
                        )
                        state["metadata"] = metadata
                        return state
                except Exception as e:
                    logger.warning("Redis vector cache lookup failed: %s", e)

        # === 3) Legacy semantic cache (only when Redis not enabled) ===
        if getattr(pipeline, "semantic_cache", None) and not getattr(pipeline, "use_redis_cache", False):
            try:
                cached = pipeline.semantic_cache.get(rewritten_query, [])  # type: ignore[attr-defined]
                if cached:
                    answer, sources = cached
                    state.update(
                        {
                            "early_answer": answer,
                            "early_sources": sources,
                            "early_cache_type": "semantic",
                        }
                    )
                    metadata.update(
                        {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cost_usd": 0.0,
                            "cache_hit": True,
                            "cache_type": "semantic",
                            "rewritten_query": rewritten_query if rewritten_query else None,
                        }
                    )
                    state["metadata"] = metadata
                    return state
            except Exception as e:
                logger.warning("Legacy semantic cache lookup failed: %s", e)

        state["metadata"] = metadata
        return state

    return semantic_cache


