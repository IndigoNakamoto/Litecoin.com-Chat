import pytest

from langchain_core.documents import Document

from backend.rag_graph.graph import build_rag_graph
from backend.rag_graph.nodes.factory import build_nodes


class _DummyExactCache:
    def __init__(self, answer: str, sources):
        self._answer = answer
        self._sources = sources

    def get(self, query_text, history_pairs):
        return (self._answer, self._sources)

    def set(self, *args, **kwargs):
        return None


class _DummyRedisVectorCache:
    def __init__(self, answer: str, sources_data):
        self._answer = answer
        self._sources_data = sources_data

    async def get(self, vector):
        return (self._answer, self._sources_data)


class _DummyInfinity:
    dimension = 1024

    async def embed_query(self, query: str):
        return [0.0] * self.dimension, None


class _DummyRetriever:
    def __init__(self, docs):
        self._docs = docs

    async def ainvoke(self, query: str):
        return self._docs


class _FakePipeline:
    # Minimal surface required by nodes
    def __init__(self):
        self.strong_ambiguous_tokens = {"it", "this", "that"}
        self.strong_prefixes = ("and ", "also ")
        self.use_intent_classification = False
        self.use_redis_cache = False
        self.use_infinity_embeddings = False
        self.use_faq_indexing = False
        self.retriever_k = 3
        self.sparse_rerank_limit = 3
        self.monitoring_enabled = False
        self.model_name = "dummy"
        self.generic_user_error_message = "ERR"
        self.no_kb_match_response = "NO_MATCH"

        self.query_cache = None
        self.semantic_cache = None
        self.hybrid_retriever = None

    def _truncate_chat_history(self, history_pairs):
        return history_pairs

    def get_infinity_embeddings(self):
        return None

    def get_redis_vector_cache(self):
        return None

    def get_intent_classifier(self):
        return None

    def get_suggested_question_cache(self):
        return None


@pytest.mark.asyncio
async def test_graph_early_return_exact_cache():
    pipeline = _FakePipeline()
    cached_doc = Document(page_content="cached", metadata={"status": "published"})
    pipeline.query_cache = _DummyExactCache("cached-answer", [cached_doc])

    graph = build_rag_graph(build_nodes(pipeline))
    state = await graph.ainvoke({"raw_query": "q", "chat_history_pairs": [], "metadata": {}})

    assert state["early_answer"] == "cached-answer"
    assert len(state["early_sources"]) == 1
    assert state["early_cache_type"] == "exact"


@pytest.mark.asyncio
async def test_graph_early_return_redis_vector_cache():
    pipeline = _FakePipeline()
    pipeline.use_redis_cache = True
    pipeline.use_infinity_embeddings = True

    pipeline.get_infinity_embeddings = lambda: _DummyInfinity()
    sources_data = [{"page_content": "x", "metadata": {"status": "published"}}]
    pipeline.get_redis_vector_cache = lambda: _DummyRedisVectorCache("redis-answer", sources_data)

    graph = build_rag_graph(build_nodes(pipeline))
    state = await graph.ainvoke({"raw_query": "q", "chat_history_pairs": [], "metadata": {}})

    assert state["early_answer"] == "redis-answer"
    assert state["early_cache_type"] == "redis_vector"
    assert len(state["early_sources"]) == 1
    assert state["early_sources"][0].metadata["status"] == "published"


@pytest.mark.asyncio
async def test_graph_skip_cache_bypasses_exact_and_vector_caches():
    """`skip_cache` (golden eval) must fall through every cache tier to retrieval."""
    pipeline = _FakePipeline()
    pipeline.use_redis_cache = True
    pipeline.use_infinity_embeddings = True
    pipeline.get_infinity_embeddings = lambda: _DummyInfinity()
    pipeline.query_cache = _DummyExactCache("cached-answer", [Document(page_content="c", metadata={"status": "published"})])
    pipeline.get_redis_vector_cache = lambda: _DummyRedisVectorCache("redis-answer", [{"page_content": "x", "metadata": {"status": "published"}}])
    live = Document(page_content="live doc", metadata={"status": "published", "doc_title": "Live"})
    pipeline.hybrid_retriever = _DummyRetriever([live])

    graph = build_rag_graph(build_nodes(pipeline))
    state = await graph.ainvoke({"raw_query": "q", "chat_history_pairs": [], "metadata": {}, "skip_cache": True})

    assert state.get("early_answer") is None
    assert state["metadata"].get("cache_bypassed") is True
    # Embedding still happened (retrieve needs the vector); retrieval ran.
    assert state.get("query_vector") is not None
    assert [d.page_content for d in state.get("published_sources") or []] == ["live doc"]

    # Same pipeline without the flag still short-circuits on the exact cache.
    state2 = await graph.ainvoke({"raw_query": "q", "chat_history_pairs": [], "metadata": {}})
    assert state2["early_answer"] == "cached-answer"


class _ScoringRetriever:
    """Returns docs that already carry a cross-encoder `rerank_score` (as the reranker would set)."""

    def __init__(self, scores):
        self._scores = scores

    async def ainvoke(self, query: str):
        return [
            Document(page_content=f"doc {i}", metadata={"status": "published", "rerank_score": s})
            for i, s in enumerate(self._scores)
        ]


@pytest.mark.asyncio
async def test_retrieve_flags_low_similarity_from_cross_encoder_score(monkeypatch):
    monkeypatch.setenv("RAG_ABSTAIN_CE_SCORE", "-3.0")
    monkeypatch.setenv("RAG_ABSTAIN_L2_DISTANCE", "0")
    monkeypatch.setattr("backend.rag_graph.nodes.retrieve.USE_CROSS_ENCODER_RERANK", False)  # scores are pre-set on the docs

    pipeline = _FakePipeline()
    pipeline.hybrid_retriever = _ScoringRetriever([-11.2, -12.0, -9.8])  # sourdough-class query
    graph = build_rag_graph(build_nodes(pipeline))
    state = await graph.ainvoke({"raw_query": "best sourdough recipe", "chat_history_pairs": [], "metadata": {}})
    assert state["low_similarity"] is True
    assert state["metadata"]["ce_top_score"] == pytest.approx(-9.8)
    # docs are kept (a flagged web search may still use the flag, not the docs)
    assert len(state["published_sources"]) == 3

    pipeline.hybrid_retriever = _ScoringRetriever([4.4, 0.1, -1.4])  # on-topic
    graph = build_rag_graph(build_nodes(pipeline))
    state = await graph.ainvoke({"raw_query": "what is mweb", "chat_history_pairs": [], "metadata": {}})
    assert state["low_similarity"] is False


@pytest.mark.asyncio
async def test_retrieve_no_ce_scores_does_not_abstain(monkeypatch):
    monkeypatch.setenv("RAG_ABSTAIN_CE_SCORE", "-3.0")
    monkeypatch.setattr("backend.rag_graph.nodes.retrieve.USE_CROSS_ENCODER_RERANK", False)
    pipeline = _FakePipeline()
    pipeline.hybrid_retriever = _DummyRetriever([Document(page_content="a", metadata={"status": "published"})])
    graph = build_rag_graph(build_nodes(pipeline))
    state = await graph.ainvoke({"raw_query": "q", "chat_history_pairs": [], "metadata": {}})
    assert state["low_similarity"] is False
    assert "ce_top_score" not in state["metadata"]


@pytest.mark.asyncio
async def test_retrieve_ce_floor_can_be_disabled(monkeypatch):
    monkeypatch.setenv("RAG_ABSTAIN_CE_SCORE", "off")
    monkeypatch.setattr("backend.rag_graph.nodes.retrieve.USE_CROSS_ENCODER_RERANK", False)
    pipeline = _FakePipeline()
    pipeline.hybrid_retriever = _ScoringRetriever([-11.0])
    graph = build_rag_graph(build_nodes(pipeline))
    state = await graph.ainvoke({"raw_query": "q", "chat_history_pairs": [], "metadata": {}})
    assert state["low_similarity"] is False


@pytest.mark.asyncio
async def test_graph_retrieve_filters_published_sources():
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
    assert state["published_sources"][0].page_content == "a"


