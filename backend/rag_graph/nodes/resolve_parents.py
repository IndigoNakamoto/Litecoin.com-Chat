from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.documents import Document

from ..state import RAGState


def make_resolve_parents_node(pipeline: Any):
    async def resolve_parents(state: RAGState) -> RAGState:
        """
        Parent-document pattern resolution for synthetic FAQ question hits.

        If FAQ indexing is enabled, swap synthetic question hits with their parent chunks.
        """
        metadata: Dict[str, Any] = state.get("metadata") or {}
        context_docs: List[Document] = state.get("context_docs") or []

        if not getattr(pipeline, "use_faq_indexing", False) or not context_docs:
            state["metadata"] = metadata
            return state

        logger = logging.getLogger(__name__)

        synthetic_count = sum(1 for d in context_docs if d.metadata.get("is_synthetic", False))
        if synthetic_count <= 0:
            state["metadata"] = metadata
            return state

        import time as _time

        _t0 = _time.perf_counter()
        try:
            from backend.services.faq_generator import resolve_parents as resolve_parents_fn

            parent_chunks_map = pipeline._load_parent_chunks_map() if hasattr(pipeline, "_load_parent_chunks_map") else {}
            if parent_chunks_map:
                # Best cross-encoder score per parent, taken from the synthetic question hits,
                # so abstention still has a relevance signal after the swap.
                best_by_parent: Dict[str, float] = {}
                for d in context_docs:
                    pid = d.metadata.get("parent_chunk_id")
                    score = d.metadata.get("rerank_score")
                    if d.metadata.get("is_synthetic") and pid and isinstance(score, (int, float)):
                        best_by_parent[pid] = max(best_by_parent.get(pid, float("-inf")), float(score))
                resolved = resolve_parents_fn(context_docs, parent_chunks_map)
                if best_by_parent:
                    # Parent docs come from a shared, cached map: copy before annotating so a
                    # score from this request never leaks into the next one.
                    patched: List[Document] = []
                    for d in resolved:
                        cid = d.metadata.get("chunk_id")
                        if cid in best_by_parent and "rerank_score" not in d.metadata:
                            d = Document(page_content=d.page_content, metadata={**d.metadata, "rerank_score": best_by_parent[cid]})
                        patched.append(d)
                    resolved = patched
                state["context_docs"] = resolved
                state["published_sources"] = [d for d in resolved if d.metadata.get("status") == "published"]
        except Exception as e:
            logger.warning("FAQ parent resolution failed; using original docs: %s", e)
        _dt = _time.perf_counter() - _t0
        metadata["t_parents_ms"] = round(_dt * 1000, 1)
        try:
            from backend.monitoring.metrics import rag_stage_duration_seconds

            rag_stage_duration_seconds.labels(stage="parents").observe(_dt)
        except Exception:
            pass

        state["metadata"] = metadata
        return state

    return resolve_parents


