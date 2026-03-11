from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage


class RAGState(TypedDict, total=False):
    """
    Shared LangGraph state for the RAG pipeline.

    We keep this as a TypedDict (instead of Pydantic) to minimize overhead and
    keep node functions simple and testable.
    """

    # Inputs
    raw_query: str
    chat_history_pairs: List[Tuple[str, str]]

    # Sanitized + normalized
    sanitized_query: str
    normalized_query: str
    truncated_history_pairs: List[Tuple[str, str]]

    # Routing / rewriting
    effective_query: str
    complexity_route: str
    is_dependent: bool
    effective_history_pairs: List[Tuple[str, str]]
    converted_history_messages: List[BaseMessage]

    # Intent / early return
    intent: Optional[str]
    matched_faq: Optional[str]
    static_answer: Optional[str]
    early_answer: Optional[str]
    early_sources: List[Document]
    early_cache_type: Optional[str]

    # Cache / embeddings
    rewritten_query: str
    rewritten_query_for_cache: str
    query_vector: Optional[List[float]]
    query_sparse: Optional[Dict[str, float]]

    # Retrieval
    retrieval_query: str
    retrieval_queries: List[str]
    context_docs: List[Document]
    published_sources: List[Document]
    retrieval_failed: bool

    # Errors
    error_type: Optional[str]
    error_message: Optional[str]

    # Metadata
    metadata: Dict[str, Any]


