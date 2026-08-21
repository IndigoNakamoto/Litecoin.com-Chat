"""C2: retrieve uses stored sparse_embedding; ingest helpers persist it."""

import pytest
from langchain_core.documents import Document

from backend.data_ingestion.vector_store_manager import (
    mongo_chunk_document,
    sparse_embedding_from_infinity_item,
)
from backend.rag_graph.nodes import retrieve as retrieve_mod
from backend.rag_graph.nodes.retrieve import make_retrieve_node


class _DummyVectorStore:
    def __init__(self, results):
        self._results = results

    def similarity_search_with_score_by_vector(self, query_vector, k: int):
        return self._results[:k]


class _DummyVectorStoreManager:
    def __init__(self, vector_store):
        self.vector_store = vector_store


class _DummyInfinity:
    def __init__(self):
        self.embed_calls = 0

    async def embed_documents(self, texts):
        self.embed_calls += 1
        return [[0.1] * 4 for _ in texts], [{"fallback": 1.0} for _ in texts]

    @staticmethod
    def sparse_similarity(query_sparse, doc_sparse):
        if not query_sparse or not doc_sparse:
            return 0.0
        if "keep" in doc_sparse:
            return 1.0
        if "fallback" in doc_sparse:
            return 0.5
        return 0.1


class _FakePipeline:
    def __init__(self, vector_results, infinity):
        self.use_infinity_embeddings = True
        self.vector_store_manager = _DummyVectorStoreManager(_DummyVectorStore(vector_results))
        self.bm25_retriever = None
        self.hybrid_retriever = None
        self.retriever_k = 2
        self.sparse_rerank_limit = 2
        self.short_query_word_threshold = 3
        self._infinity = infinity

    def get_infinity_embeddings(self):
        return self._infinity


def _doc(content: str, sparse=None, status="published"):
    md = {"status": status}
    if sparse is not None:
        md["sparse_embedding"] = sparse
    return Document(page_content=content, metadata=md)


@pytest.mark.asyncio
async def test_retrieve_uses_stored_sparse_without_reembed(monkeypatch):
    monkeypatch.setattr(retrieve_mod, "USE_CROSS_ENCODER_RERANK", False)
    kept = _doc("keep-me", {"keep": 1.0})
    other = _doc("other", {"other": 1.0})
    infinity = _DummyInfinity()
    pipeline = _FakePipeline([(kept, 0.4), (other, 0.5)], infinity)
    node = make_retrieve_node(pipeline)

    state = await node(
        {
            "retrieval_query": "mweb",
            "metadata": {},
            "query_vector": [0.0] * 8,
            "query_sparse": {"keep": 1.0},
        }
    )

    assert infinity.embed_calls == 0
    assert [d.page_content for d in state["context_docs"]] == ["keep-me", "other"]


@pytest.mark.asyncio
async def test_retrieve_embeds_only_chunks_missing_sparse(monkeypatch):
    monkeypatch.setattr(retrieve_mod, "USE_CROSS_ENCODER_RERANK", False)
    stored = _doc("stored", {"keep": 1.0})
    missing = _doc("missing-sparse")
    infinity = _DummyInfinity()
    pipeline = _FakePipeline([(stored, 0.4), (missing, 0.5)], infinity)
    node = make_retrieve_node(pipeline)

    state = await node(
        {
            "retrieval_query": "mweb",
            "metadata": {},
            "query_vector": [0.0] * 8,
            "query_sparse": {"keep": 1.0},
        }
    )

    assert infinity.embed_calls == 1
    assert state["context_docs"][0].page_content == "stored"


@pytest.mark.asyncio
async def test_retrieve_skips_sparse_when_top_faiss_distance_is_low(monkeypatch):
    monkeypatch.setattr(retrieve_mod, "USE_CROSS_ENCODER_RERANK", False)
    monkeypatch.setenv("SPARSE_RERANK_SKIP_DISTANCE", "0.2")
    first = _doc("close", {"other": 1.0})
    second = _doc("keep-me", {"keep": 1.0})
    infinity = _DummyInfinity()
    pipeline = _FakePipeline([(first, 0.01), (second, 0.9)], infinity)
    node = make_retrieve_node(pipeline)

    state = await node(
        {
            "retrieval_query": "mweb",
            "metadata": {},
            "query_vector": [0.0] * 8,
            "query_sparse": {"keep": 1.0},
        }
    )

    assert infinity.embed_calls == 0
    assert [d.page_content for d in state["context_docs"]] == ["close", "keep-me"]


def test_sparse_embedding_from_infinity_item():
    assert sparse_embedding_from_infinity_item({"embedding": [0.1]}) is None
    assert sparse_embedding_from_infinity_item({"sparse_embedding": {}}) is None
    assert sparse_embedding_from_infinity_item({"sparse_embedding": {"tok": 0.5}}) == {"tok": 0.5}


def test_mongo_chunk_document_persists_sparse_top_level_and_metadata():
    doc = mongo_chunk_document("chunk", {"status": "published"}, [0.1, 0.2], {"tok": 1.0})
    assert doc["sparse_embedding"] == {"tok": 1.0}
    assert doc["metadata"]["sparse_embedding"] == {"tok": 1.0}
    assert doc["embedding"] == [0.1, 0.2]

    dense_only = mongo_chunk_document("chunk", {"status": "published"}, [0.1])
    assert "sparse_embedding" not in dense_only
