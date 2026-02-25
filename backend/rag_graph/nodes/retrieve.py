from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document

from ..state import RAGState

USE_CROSS_ENCODER_RERANK = os.getenv("USE_CROSS_ENCODER_RERANK", "true").lower() == "true"


def make_retrieve_node(pipeline: Any):

    async def _retrieve_single_query(
        query_text: str,
        query_vector: Optional[List[float]],
        query_sparse: Optional[Dict[str, float]],
        retriever_k: int,
        sparse_rerank_limit: int,
        is_short_query: bool,
        use_infinity: bool,
        logger: logging.Logger,
    ) -> Tuple[List[Document], bool]:
        """Run retrieval for a single query. Returns (docs, retrieval_failed)."""
        context_docs: List[Document] = []
        retrieval_failed = False

        if use_infinity and query_vector is not None and getattr(pipeline, "vector_store_manager", None):
            infinity = pipeline.get_infinity_embeddings() if hasattr(pipeline, "get_infinity_embeddings") else None
            vector_docs: List[Document] = []
            bm25_docs: List[Document] = []

            try:
                def run_vector_search():
                    return pipeline.vector_store_manager.vector_store.similarity_search_with_score_by_vector(
                        query_vector, k=retriever_k * 2
                    )

                def run_bm25_search():
                    bm25 = getattr(pipeline, "bm25_retriever", None)
                    if not bm25:
                        return []
                    original_k = getattr(bm25, "k", retriever_k)
                    bm25.k = retriever_k * (4 if is_short_query else 2)
                    try:
                        return bm25.invoke(query_text)
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

                vector_docs = [doc for doc, _score in (vector_results or [])[:retriever_k]]

            except Exception as e:
                logger.warning("Infinity parallel retrieval failed; falling back: %s", e, exc_info=True)
                vector_docs = []
                bm25_docs = []

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
                    if len(reranked) < retriever_k and len(candidate_docs) > len(candidates_for_rerank):
                        remaining = [d for d in candidate_docs[sparse_rerank_limit:] if d not in reranked]
                        reranked.extend(remaining[: max(retriever_k - len(reranked), 0)])
                    context_docs = reranked[:retriever_k]
                except Exception as e:
                    logger.warning("Sparse re-ranking failed; using basic hybrid: %s", e, exc_info=True)
                    context_docs = candidate_docs[:retriever_k]
            else:
                context_docs = candidate_docs[:retriever_k]

            if not context_docs:
                try:
                    retriever = getattr(pipeline, "hybrid_retriever", None)
                    if retriever and hasattr(retriever, "ainvoke"):
                        context_docs = await retriever.ainvoke(query_text)
                        retrieval_failed = True
                except Exception:
                    retrieval_failed = True
                    context_docs = []
        else:
            retriever = getattr(pipeline, "hybrid_retriever", None)
            try:
                if retriever and hasattr(retriever, "ainvoke"):
                    context_docs = await retriever.ainvoke(query_text)
                else:
                    context_docs = []
            except Exception:
                retrieval_failed = True
                context_docs = []

        return context_docs, retrieval_failed

    async def retrieve(state: RAGState) -> RAGState:
        """
        Retrieval node.

        Supports multi-query retrieval: if the decompose node produced multiple
        sub-queries, each is retrieved independently and results are merged.
        After merging, an optional cross-encoder re-ranks for relevance.
        """
        metadata: Dict[str, Any] = state.get("metadata") or {}

        if state.get("early_answer") is not None:
            state["metadata"] = metadata
            return state

        logger = logging.getLogger(__name__)

        primary_query = (
            state.get("retrieval_query")
            or state.get("rewritten_query")
            or state.get("effective_query")
            or state.get("sanitized_query")
            or ""
        )
        retrieval_queries: List[str] = state.get("retrieval_queries") or [primary_query]
        if not retrieval_queries:
            retrieval_queries = [primary_query]

        retriever_k = int(getattr(pipeline, "retriever_k", 12))
        sparse_rerank_limit = int(getattr(pipeline, "sparse_rerank_limit", 10))

        use_infinity = bool(getattr(pipeline, "use_infinity_embeddings", False))
        pre_computed_vector = state.get("query_vector")
        pre_computed_sparse = state.get("query_sparse")

        is_multi_query = len(retrieval_queries) > 1

        all_docs: List[Document] = []
        any_failed = False

        for idx, sub_query in enumerate(retrieval_queries):
            try:
                short_threshold = int(getattr(pipeline, "short_query_word_threshold", 3) or 3)
                _tokens = re.findall(r"[a-z0-9']+", (sub_query or "").lower())
                is_short_query = 0 < len(_tokens) <= short_threshold
            except Exception:
                is_short_query = False

            if idx == 0 and not is_multi_query:
                q_vector = pre_computed_vector
                q_sparse = pre_computed_sparse
            else:
                q_vector = None
                q_sparse = None
                if use_infinity:
                    infinity = pipeline.get_infinity_embeddings() if hasattr(pipeline, "get_infinity_embeddings") else None
                    if infinity:
                        try:
                            q_vector, q_sparse = await infinity.embed_query(sub_query)
                        except Exception as e:
                            logger.warning("Failed to embed sub-query %d: %s", idx, e)

            per_query_k = retriever_k if not is_multi_query else max(retriever_k // len(retrieval_queries) + 2, 6)

            docs, failed = await _retrieve_single_query(
                query_text=sub_query,
                query_vector=q_vector,
                query_sparse=q_sparse,
                retriever_k=per_query_k,
                sparse_rerank_limit=sparse_rerank_limit,
                is_short_query=is_short_query,
                use_infinity=use_infinity,
                logger=logger,
            )
            all_docs.extend(docs)
            if failed:
                any_failed = True

            logger.debug(
                "Retrieve sub-query %d/%d: query='%s', docs=%d, failed=%s",
                idx + 1, len(retrieval_queries), sub_query[:80], len(docs), failed,
            )

        if is_multi_query:
            seen = set()
            deduped: List[Document] = []
            for doc in all_docs:
                key = doc.page_content[:200]
                if key not in seen:
                    seen.add(key)
                    deduped.append(doc)
            context_docs = deduped[:retriever_k]
            logger.info(
                "Multi-query merge: %d total -> %d deduped -> %d kept (k=%d)",
                len(all_docs), len(deduped), len(context_docs), retriever_k,
            )
        else:
            context_docs = all_docs

        # Cross-encoder re-ranking
        if USE_CROSS_ENCODER_RERANK and context_docs and primary_query:
            try:
                from backend.services.cross_encoder_reranker import CrossEncoderReranker

                reranker = CrossEncoderReranker.get_instance()
                cross_encoder_top_k = int(os.getenv("CROSS_ENCODER_TOP_K", str(retriever_k)))
                context_docs = reranker.rerank(primary_query, context_docs, top_k=cross_encoder_top_k)
                logger.debug(
                    "Cross-encoder re-ranked %d docs, kept top %d",
                    len(all_docs) if is_multi_query else len(context_docs),
                    len(context_docs),
                )
            except Exception as e:
                logger.warning("Cross-encoder re-ranking failed; using original order: %s", e)

        # Debug logging for retrieval diagnostics
        if logger.isEnabledFor(logging.DEBUG) and context_docs:
            for i, doc in enumerate(context_docs[:5]):
                title = doc.metadata.get("doc_title", doc.metadata.get("doc_title_hierarchical", "?"))
                section = doc.metadata.get("section_title", "")
                status = doc.metadata.get("status", "?")
                logger.debug(
                    "Retrieve result [%d]: title='%s', section='%s', status=%s, len=%d",
                    i, title, section, status, len(doc.page_content),
                )

        published_sources = [d for d in context_docs if d.metadata.get("status") == "published"]
        if context_docs and not published_sources:
            logger.warning(
                "Retrieve: context_docs=%s but published_sources=0 (no doc has metadata.status==\"published\")",
                len(context_docs),
            )

        unpublished_count = len(context_docs) - len(published_sources)
        if unpublished_count > 0:
            logger.debug("Retrieve: filtered %d unpublished docs from %d total", unpublished_count, len(context_docs))

        state.update(
            {
                "context_docs": context_docs,
                "published_sources": published_sources,
                "retrieval_failed": any_failed,
            }
        )
        state["metadata"] = metadata
        return state

    return retrieve
