"""C1: multi-query retrieve runs concurrently."""

import asyncio

import pytest
from langchain_core.documents import Document

from backend.rag_graph.nodes import retrieve as retrieve_mod
from backend.rag_graph.nodes.retrieve import make_retrieve_node


class _ConcurrentRetriever:
    def __init__(self):
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls = []

    async def ainvoke(self, query: str):
        self.calls.append(query)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.05)
        self.in_flight -= 1
        return [Document(page_content=f"hit:{query}", metadata={"status": "published"})]


class _FakePipeline:
    def __init__(self, retriever):
        self.use_infinity_embeddings = False
        self.vector_store_manager = None
        self.bm25_retriever = None
        self.hybrid_retriever = retriever
        self.retriever_k = 4
        self.sparse_rerank_limit = 4
        self.short_query_word_threshold = 3


@pytest.mark.asyncio
async def test_multi_query_retrieve_runs_concurrently(monkeypatch):
    monkeypatch.setattr(retrieve_mod, "USE_CROSS_ENCODER_RERANK", False)
    retriever = _ConcurrentRetriever()
    node = make_retrieve_node(_FakePipeline(retriever))

    state = await node(
        {
            "retrieval_query": "primary",
            "retrieval_queries": ["alpha", "beta", "gamma"],
            "metadata": {},
        }
    )

    assert retriever.max_in_flight >= 2
    assert set(retriever.calls) == {"alpha", "beta", "gamma"}
    contents = {d.page_content for d in state["context_docs"]}
    assert contents == {"hit:alpha", "hit:beta", "hit:gamma"}
    assert len(state["published_sources"]) == 3
