"""Non-stream answer generation: chain select, format_docs, ainvoke, grounding, cache write-back.

Called by the thin LangGraph `generate` node and as a fallback from `RAGPipeline.aquery`.
Streaming stays in `rag_pipeline.astream_query` for this slice.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage

from backend.rag_context_format import format_docs
from backend.rag_graph.state import RAGState

logger = logging.getLogger(__name__)


async def generate_answer(pipeline: Any, state: RAGState) -> RAGState:
    """Run non-stream generation and write `generated_answer` onto state.

    No-ops when there is already an early answer, an error, no published sources,
    or the pipeline has no document chain (graph unit tests).
    """
    metadata: Dict[str, Any] = state.get("metadata") or {}

    if state.get("early_answer") is not None or state.get("error_message") is not None:
        state["metadata"] = metadata
        return state

    if state.get("skip_generation"):
        state["metadata"] = metadata
        return state

    published_sources: List[Document] = state.get("published_sources") or []
    context_docs: List[Document] = state.get("context_docs") or []
    if not published_sources:
        state["metadata"] = metadata
        return state

    if not getattr(pipeline, "document_chain_simple", None) and not getattr(
        pipeline, "document_chain_complex", None
    ):
        state["metadata"] = metadata
        return state

    converted_history: List[BaseMessage] = state.get("converted_history_messages") or []
    sanitized_query = (
        state.get("sanitized_query") or state.get("raw_query") or ""
    )
    active_chain, response_profile, active_instruction = pipeline._select_document_chain(state)
    metadata["response_profile"] = response_profile

    llm_start = time.time()
    context_text = format_docs(context_docs)

    coverage_note = ""
    missing: List[str] = []
    if getattr(pipeline, "search_grounding_enabled", False):
        missing = pipeline._find_missing_query_terms(sanitized_query, published_sources)
        if missing:
            coverage_note = (
                "IMPORTANT: The provided context does NOT contain information about: "
                f"{', '.join(missing)}. You MUST use Google Search for these topics."
            )

    answer_result = await active_chain.ainvoke(
        {
            "input": sanitized_query,
            "context": context_text,
            "context_coverage_note": coverage_note,
            "chat_history": converted_history,
        }
    )
    answer = answer_result.content if hasattr(answer_result, "content") else str(answer_result)
    llm_duration = time.time() - llm_start

    grounding_meta = None
    if hasattr(pipeline, "_extract_grounding_metadata"):
        grounding_meta = pipeline._extract_grounding_metadata(answer_result)
    is_grounded = grounding_meta is not None and bool(grounding_meta.get("grounding_chunks"))

    if not is_grounded and coverage_note and answer:
        missing_in_answer = [t for t in missing if t in answer.lower()]
        if missing_in_answer:
            is_grounded = True
            logger.info(
                "Coverage-gap fallback (generate): missing terms %s in answer → grounded",
                missing_in_answer,
            )

    input_tokens, output_tokens = 0, 0
    cost_usd = 0.0
    if getattr(pipeline, "monitoring_enabled", False):
        if hasattr(pipeline, "_extract_token_usage_from_llm_response"):
            input_tokens, output_tokens = pipeline._extract_token_usage_from_llm_response(
                answer_result
            )
        if input_tokens == 0 and output_tokens == 0 and hasattr(pipeline, "_estimate_token_usage"):
            prompt_text = pipeline._build_prompt_text_with_history(
                sanitized_query,
                context_text,
                converted_history,
                system_instruction=active_instruction,
            )
            input_tokens, output_tokens = pipeline._estimate_token_usage(prompt_text, answer)
        if hasattr(pipeline, "estimate_gemini_cost"):
            cost_usd = pipeline.estimate_gemini_cost(
                input_tokens, output_tokens, pipeline.model_name
            )
        if hasattr(pipeline, "track_llm_metrics"):
            pipeline.track_llm_metrics(
                model=pipeline.model_name,
                operation="generate",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                duration_seconds=llm_duration,
                status="success",
            )
        try:
            if hasattr(pipeline, "record_spend"):
                await pipeline.record_spend(
                    cost_usd, input_tokens, output_tokens, pipeline.model_name
                )
        except Exception as e:
            logger.warning("Error recording spend: %s", e, exc_info=True)

    query_text = state.get("raw_query") or sanitized_query
    effective_history = state.get("effective_history_pairs") or []
    query_cache = getattr(pipeline, "query_cache", None)
    if query_cache is not None:
        query_cache.set(query_text, effective_history, answer, published_sources)

    query_vector = state.get("query_vector")
    rewritten_query = state.get("rewritten_query_for_cache") or state.get("rewritten_query") or ""
    if getattr(pipeline, "use_redis_cache", False) and query_vector:
        redis_cache = (
            pipeline.get_redis_vector_cache()
            if hasattr(pipeline, "get_redis_vector_cache")
            else None
        )
        if redis_cache:
            try:
                sources_data = [
                    {"page_content": d.page_content, "metadata": d.metadata}
                    for d in published_sources
                ]
                await redis_cache.set(query_vector, rewritten_query, answer, sources_data)
            except Exception as e:
                logger.warning("Redis cache storage failed: %s", e)
    semantic_cache = getattr(pipeline, "semantic_cache", None)
    if semantic_cache and not getattr(pipeline, "use_redis_cache", False):
        semantic_cache.set(rewritten_query, [], answer, published_sources)

    metadata.update(
        {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "cache_hit": False,
            "cache_type": None,
            "rewritten_query": rewritten_query
            if rewritten_query and rewritten_query != query_text
            else None,
            "response_profile": response_profile,
            "complexity_route": state.get("complexity_route"),
            "grounding_metadata": grounding_meta,
            "is_grounded": is_grounded,
        }
    )
    state["generated_answer"] = answer
    state["grounding_metadata"] = grounding_meta
    state["metadata"] = metadata
    return state
