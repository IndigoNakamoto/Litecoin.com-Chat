"""C3: thin generate node + rag.generate helper."""

import pytest
from langchain_core.documents import Document

from backend.rag.generate import generate_answer
from backend.rag_graph.graph import build_rag_graph
from backend.rag_graph.nodes.factory import build_nodes
from backend.rag_graph.nodes.generate import make_generate_node
from backend.tests.test_rag_graph_state_machine import _DummyRetriever, _FakePipeline


class _DummyCache:
    def __init__(self):
        self.sets = []

    def set(self, *args, **kwargs):
        self.sets.append((args, kwargs))


class _DummyChain:
    def __init__(self, text="generated-answer"):
        self.text = text
        self.calls = 0

    async def ainvoke(self, payload):
        self.calls += 1

        class _R:
            content = self.text
            response_metadata = {}

        return _R()


class _GeneratePipeline:
    def __init__(self):
        self.document_chain_simple = _DummyChain()
        self.document_chain_complex = self.document_chain_simple
        self._simple_instruction = "simple"
        self._complex_instruction = "complex"
        self.search_grounding_enabled = False
        self.monitoring_enabled = False
        self.query_cache = _DummyCache()
        self.semantic_cache = None
        self.use_redis_cache = False
        self.model_name = "dummy"

    def _select_document_chain(self, state):
        return self.document_chain_simple, "simple", self._simple_instruction

    def _extract_grounding_metadata(self, response):
        return None


@pytest.mark.asyncio
async def test_generate_answer_writes_generated_answer_and_cache():
    pipeline = _GeneratePipeline()
    docs = [Document(page_content="Litecoin is a peer-to-peer currency.", metadata={"status": "published", "slug": "intro"})]
    state = await generate_answer(
        pipeline,
        {
            "raw_query": "What is Litecoin?",
            "sanitized_query": "What is Litecoin?",
            "context_docs": docs,
            "published_sources": docs,
            "converted_history_messages": [],
            "effective_history_pairs": [],
            "metadata": {},
        },
    )
    assert state["generated_answer"] == "generated-answer"
    assert pipeline.document_chain_simple.calls == 1
    assert len(pipeline.query_cache.sets) == 1
    assert state["metadata"]["response_profile"] == "simple"


@pytest.mark.asyncio
async def test_generate_node_skips_when_streaming_flag_set():
    pipeline = _GeneratePipeline()
    node = make_generate_node(pipeline)
    docs = [Document(page_content="x", metadata={"status": "published"})]
    state = await node(
        {
            "skip_generation": True,
            "published_sources": docs,
            "context_docs": docs,
            "metadata": {},
        }
    )
    assert state.get("generated_answer") is None
    assert pipeline.document_chain_simple.calls == 0


@pytest.mark.asyncio
async def test_graph_still_retrieves_without_generation_chain():
    pipeline = _FakePipeline()
    docs = [
        Document(page_content="a", metadata={"status": "published"}),
        Document(page_content="b", metadata={"status": "draft"}),
    ]
    pipeline.hybrid_retriever = _DummyRetriever(docs)
    graph = build_rag_graph(build_nodes(pipeline))
    state = await graph.ainvoke({"raw_query": "q", "chat_history_pairs": [], "metadata": {}})
    assert len(state["context_docs"]) == 2
    assert len(state["published_sources"]) == 1
    assert state.get("generated_answer") is None
