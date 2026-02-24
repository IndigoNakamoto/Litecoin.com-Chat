from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List

from langchain_core.documents import Document

from ..state import RAGState


def make_retrieve_node(pipeline: Any):
    async def retrieve(state: RAGState) -> RAGState:
        """
        Retrieval node.

        Full behavior: when Infinity embeddings are enabled and a vector exists, run
        Infinity vector search + BM25 in parallel, then optionally sparse re-rank.
        Otherwise, fall back to the pipeline's hybrid retriever.
        """
        metadata: Dict[str, Any] = state.get("metadata") or {}

        if state.get("early_answer") is not None:
            state["metadata"] = metadata
            return state

        logger = logging.getLogger(__name__)

        retrieval_query = state.get("retrieval_query") or state.get("rewritten_query") or state.get("effective_query") or state.get("sanitized_query") or ""
        context_docs: List[Document] = []
        retrieval_failed = False

        retriever_k = int(getattr(pipeline, "retriever_k", 12))
        sparse_rerank_limit = int(getattr(pipeline, "sparse_rerank_limit", 10))
        # Short-query heuristic: boost BM25 breadth for 1–N token queries (semantic sparsity)
        try:
            import re

            short_threshold = int(getattr(pipeline, "short_query_word_threshold", 3) or 3)
            _tokens = re.findall(r"[a-z0-9']+", (retrieval_query or "").lower())
            is_short_query = 0 < len(_tokens) <= short_threshold
        except Exception:
            is_short_query = False

        use_infinity = bool(getattr(pipeline, "use_infinity_embeddings", False))
        query_vector = state.get("query_vector")
        query_sparse = state.get("query_sparse")

        # Infinity hybrid retrieval path
        if use_infinity and query_vector is not None and getattr(pipeline, "vector_store_manager", None):
            infinity = pipeline.get_infinity_embeddings() if hasattr(pipeline, "get_infinity_embeddings") else None
            vector_docs: List[Document] = []
            bm25_docs: List[Document] = []

            try:
                def run_vector_search():
                    return pipeline.vector_store_manager.vector_store.similarity_search_with_score_by_vector(  # type: ignore[attr-defined]
                        query_vector, k=retriever_k * 2
                    )

                def run_bm25_search():
                    bm25 = getattr(pipeline, "bm25_retriever", None)
                    if not bm25:
                        return []
                    original_k = getattr(bm25, "k", retriever_k)
                    bm25.k = retriever_k * (4 if is_short_query else 2)
                    try:
                        return bm25.invoke(retrieval_query)
                    finally:
                        bm25.k = original_k

                vector_task = asyncio.to_thread(run_vector_search)
                bm25 = getattr(pipeline, "bm25_retriever", None)
                bm25_task = asyncio.to_thread(run_bm25_search) if bm25 else None

                if bm25_task:
                    vector_results, bm25_docs = await asyncio.gather(vector_task, bm25_task)
                else:
                    vector_results = await vector_task
                    bm25_docs = []

                # NOTE: FAISS (via LangChain) commonly returns a *distance* score where
                # lower is better (not a similarity where higher is better).
                # Thresholding with `score >= MIN_VECTOR_SIMILARITY` can therefore drop
                # the best matches and keep worse ones. We avoid score-based filtering
                # and just take the top-K results returned by the vector store.
                vector_docs = [doc for doc, _score in (vector_results or [])[:retriever_k]]

            except Exception as e:
                logger.warning("Infinity parallel retrieval failed; falling back: %s", e, exc_info=True)
                vector_docs = []
                bm25_docs = []

            # Merge + dedupe (BM25 first)
            seen = set()
            candidate_docs: List[Document] = []
            for doc in bm25_docs:
                key = doc.page_content[:200]
                if key not in seen:
                    seen.add(key)
                    candidate_docs.append(doc)
            for doc in vector_docs:
                key = doc.page_content[:200]
                if key not in seen:
                    seen.add(key)
                    candidate_docs.append(doc)

            # Sparse re-ranking if available
            if query_sparse and infinity and candidate_docs:
                try:
                    candidates_for_rerank = candidate_docs[:sparse_rerank_limit]
                    doc_texts = [d.page_content[:8000] for d in candidates_for_rerank]
                    _, doc_sparse_list = await infinity.embed_documents(doc_texts)

                    doc_scores = []
                    for i, (doc, doc_sparse) in enumerate(zip(candidates_for_rerank, doc_sparse_list)):
                        if doc_sparse:
                            score = infinity.sparse_similarity(query_sparse, doc_sparse)
                        else:
                            score = 0.0
                        doc_scores.append((score, i, doc))

                    doc_scores.sort(reverse=True, key=lambda x: x[0])
                    reranked = [doc for _, _, doc in doc_scores]
                    # Add remaining candidates if needed
                    if len(reranked) < retriever_k and len(candidate_docs) > len(candidates_for_rerank):
                        remaining = [d for d in candidate_docs[sparse_rerank_limit:] if d not in reranked]
                        reranked.extend(remaining[: max(retriever_k - len(reranked), 0)])
                    context_docs = reranked[:retriever_k]
                except Exception as e:
                    logger.warning("Sparse re-ranking failed; using basic hybrid: %s", e, exc_info=True)
                    context_docs = candidate_docs[:retriever_k]
            else:
                context_docs = candidate_docs[:retriever_k]

            # Fallback if nothing retrieved
            if not context_docs:
                try:
                    retriever = getattr(pipeline, "hybrid_retriever", None)
                    if retriever and hasattr(retriever, "ainvoke"):
                        context_docs = await retriever.ainvoke(retrieval_query)
                        retrieval_failed = True
                except Exception:
                    retrieval_failed = True
                    context_docs = []
        else:
            # Legacy: use hybrid retriever directly.
            retriever = getattr(pipeline, "hybrid_retriever", None)
            try:
                if retriever and hasattr(retriever, "ainvoke"):
                    context_docs = await retriever.ainvoke(retrieval_query)
                else:
                    context_docs = []
            except Exception:
                retrieval_failed = True
                context_docs = []

        published_sources = [d for d in context_docs if d.metadata.get("status") == "published"]
        if context_docs and not published_sources:
            logger.warning(
                "Retrieve: context_docs=%s but published_sources=0 (no doc has metadata.status==\"published\")",
                len(context_docs),
            )
        state.update(
            {
                "context_docs": context_docs,
                "published_sources": published_sources,
                "retrieval_failed": retrieval_failed,
            }
        )
        state["metadata"] = metadata
        return state

    return retrieve


