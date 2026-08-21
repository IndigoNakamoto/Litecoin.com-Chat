"""CE skip uses stubbed FAISS L2 distance; must not load MiniLM."""

from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from backend.rag_graph.nodes import retrieve as retrieve_mod
from backend.rag_graph.nodes.retrieve import make_retrieve_node


class _DummyVectorStore:
    def __init__(self, results):
        self._results = results

    def similarity_search_with_score_by_vector(self, query_vector, k: int):
        return self._results[:k]


class _FakePipeline:
    def __init__(self, results):
        self.use_infinity_embeddings = True
        self.vector_store_manager = MagicMock()
        self.vector_store_manager.vector_store = _DummyVectorStore(results)
        self.bm25_retriever = None
        self.hybrid_retriever = None
        self.retriever_k = 2
        self.sparse_rerank_limit = 2

    def get_infinity_embeddings(self):
        return None


@pytest.mark.asyncio
async def test_cross_encoder_skipped_when_faiss_l2_is_clear(monkeypatch):
    rerank_calls = []

    class _Boom:
        def rerank(self, *args, **kwargs):
            rerank_calls.append(1)
            raise AssertionError("MiniLM rerank must not run on a clear FAISS hit")

        @classmethod
        def get_instance(cls):
            return cls()

    monkeypatch.setattr(retrieve_mod, "USE_CROSS_ENCODER_RERANK", True)
    monkeypatch.setenv("CROSS_ENCODER_SKIP_DISTANCE", "0.15")
    monkeypatch.setattr(
        "backend.services.cross_encoder_reranker.CrossEncoderReranker",
        _Boom,
    )

    close = Document(page_content="charlie lee created litecoin", metadata={"status": "published"})
    far = Document(page_content="other", metadata={"status": "published"})
    node = make_retrieve_node(_FakePipeline([(close, 0.05), (far, 0.9)]))
    state = await node(
        {
            "retrieval_query": "who is charlie lee",
            "metadata": {},
            "query_vector": [0.0] * 8,
            "query_sparse": None,
        }
    )

    assert state["metadata"].get("cross_encoder_skipped") is True
    assert state["metadata"].get("faiss_top_distance") == 0.05
    assert rerank_calls == []
    assert [d.page_content for d in state["context_docs"]] == [
        "charlie lee created litecoin",
        "other",
    ]


@pytest.mark.asyncio
async def test_cross_encoder_runs_when_faiss_l2_is_ambiguous(monkeypatch):
    rerank_calls = []

    class _Stub:
        def rerank(self, query, documents, top_k=None):
            rerank_calls.append(query)
            return documents[:top_k] if top_k else documents

        @classmethod
        def get_instance(cls):
            return cls()

    monkeypatch.setattr(retrieve_mod, "USE_CROSS_ENCODER_RERANK", True)
    monkeypatch.setenv("CROSS_ENCODER_SKIP_DISTANCE", "0.15")
    monkeypatch.setattr(
        "backend.services.cross_encoder_reranker.CrossEncoderReranker",
        _Stub,
    )

    a = Document(page_content="a", metadata={"status": "published"})
    b = Document(page_content="b", metadata={"status": "published"})
    node = make_retrieve_node(_FakePipeline([(a, 0.40), (b, 0.50)]))
    state = await node(
        {
            "retrieval_query": "mweb",
            "metadata": {},
            "query_vector": [0.0] * 8,
            "query_sparse": None,
        }
    )

    assert state["metadata"].get("cross_encoder_skipped") is False
    assert state["metadata"].get("faiss_top_distance") == 0.40
    assert rerank_calls == ["mweb"]
