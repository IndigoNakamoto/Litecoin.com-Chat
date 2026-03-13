from __future__ import annotations

import logging
import os
import threading
from typing import List, Optional

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """
    Singleton cross-encoder re-ranker using a HuggingFace model.

    Scores each (query, document) pair for relevance and re-sorts results.
    The model is lazy-loaded on first use and cached for subsequent calls.
    """

    _instance: Optional[CrossEncoderReranker] = None
    _lock = threading.Lock()

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name or os.getenv("CROSS_ENCODER_MODEL", DEFAULT_MODEL)
        self._model = None

    @classmethod
    def get_instance(cls) -> CrossEncoderReranker:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading cross-encoder model: %s", self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("Cross-encoder model loaded successfully")
        except Exception as e:
            logger.error("Failed to load cross-encoder model '%s': %s", self._model_name, e)
            raise

    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: Optional[int] = None,
    ) -> List[Document]:
        """
        Re-rank documents by relevance to the query using a cross-encoder.

        Args:
            query: The user query.
            documents: Retrieved documents to re-rank.
            top_k: Keep only the top-k results. If None, returns all re-sorted.

        Returns:
            Re-ranked list of documents, most relevant first.
        """
        if not documents or not query:
            return documents

        self._load_model()

        pairs = [(query, doc.page_content[:2048]) for doc in documents]

        try:
            scores = self._model.predict(pairs)
        except Exception as e:
            logger.warning("Cross-encoder prediction failed: %s", e)
            return documents

        scored = sorted(
            zip(scores, range(len(documents)), documents),
            key=lambda x: x[0],
            reverse=True,
        )

        for score, idx, doc in scored:
            doc.metadata["rerank_score"] = float(score)

        if logger.isEnabledFor(logging.DEBUG):
            for score, idx, doc in scored[:5]:
                title = doc.metadata.get("doc_title", doc.metadata.get("doc_title_hierarchical", "?"))
                section = doc.metadata.get("section_title", "")
                logger.debug(
                    "Cross-encoder score=%.4f: title='%s', section='%s'",
                    score, title, section,
                )

        result = [doc for _, _, doc in scored]
        if top_k is not None and top_k > 0:
            result = result[:top_k]

        return result
