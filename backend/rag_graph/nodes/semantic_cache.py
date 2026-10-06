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
        # Golden eval / explicit bypass: still embed (retrieve needs the vector) but never
        # return a cached answer from any tier.
        skip_cache = bool(state.get("skip_cache"))
        if skip_cache:
            metadata["cache_bypassed"] = True

        # === 0) Exact normalised-text cache (empty history only) ===
        # Cheapest tier: no embedding call. Keyed on the sanitized question text, so
        # it only applies when there is no conversation context to resolve.
        if not skip_cache and getattr(pipeline, "use_exact_answer_cache", False) and not state.get("chat_history_pairs"):
            exact_cache = pipeline.get_exact_answer_cache() if hasattr(pipeline, "get_exact_answer_cache") else None
            exact_key_text = state.get("sanitized_query") or state.get("raw_query") or ""
            if exact_cache and exact_key_text:
                try:
                    import time as _time

                    _t0 = _time.perf_counter()
                    entry = await exact_cache.get(exact_key_text)
                    metadata["t_exact_cache_ms"] = round((_time.perf_counter() - _t0) * 1000, 1)
                    if entry and entry.answer:
                        cached_sources = [
                            Document(page_content=src.get("page_content", ""), metadata=src.get("metadata", {}))
                            for src in entry.sources
                            if isinstance(src, dict)
                        ]
                        state.update(
                            {
                                "early_answer": entry.answer,
                                "early_sources": cached_sources,
                                "early_cache_type": "exact_redis",
                            }
                        )
                        metadata.update(
                            {
                                "input_tokens": 0,
                                "output_tokens": 0,
                                "cost_usd": 0.0,
                                "cache_hit": True,
                                "cache_type": "exact_redis",
                                "is_grounded": bool(entry.is_grounded),
                            }
                        )
                        state["metadata"] = metadata
                        return state
                except Exception as e:
                    logger.warning("Exact answer cache lookup failed: %s", e)

        # === 1) Embedding generation (Infinity) ===
        query_vector = None
        query_sparse = None

        if getattr(pipeline, "use_redis_cache", False) or getattr(pipeline, "use_infinity_embeddings", False):
            infinity = pipeline.get_infinity_embeddings() if hasattr(pipeline, "get_infinity_embeddings") else None
            if infinity:
                try:
                    import time as _time

                    _t0 = _time.perf_counter()
                    query_vector, query_sparse = await infinity.embed_query(rewritten_query)
                    metadata["t_embed_ms"] = round((_time.perf_counter() - _t0) * 1000, 1)
                    try:
                        from backend.monitoring.metrics import rag_embedding_generation_duration_seconds

                        rag_embedding_generation_duration_seconds.observe(_time.perf_counter() - _t0)
                    except Exception:
                        pass
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
        if not skip_cache and getattr(pipeline, "use_redis_cache", False) and query_vector:
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
        if not skip_cache and getattr(pipeline, "semantic_cache", None) and not getattr(pipeline, "use_redis_cache", False):
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


