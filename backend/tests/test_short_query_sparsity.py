import pytest

from langchain_core.documents import Document

from backend.rag_graph.nodes.prechecks import make_prechecks_node
from backend.rag_graph.nodes.retrieve import make_retrieve_node


class _DummyLLM:
    def __init__(self, content: str = "What is XYZ in the Litecoin knowledge base?"):
        self.calls = 0
        self.content = content

    async def ainvoke(self, messages):
        self.calls += 1

        class _R:
            content = self.content

        return _R()


class _DummyVectorStore:
    def __init__(self, results):
        self._results = results

    def similarity_search_with_score_by_vector(self, query_vector, k: int):
        # Return results in the order provided (as LangChain would after ranking).
        return self._results[:k]


class _DummyVectorStoreManager:
    def __init__(self, vector_store):
        self.vector_store = vector_store


class _FakePipeline:
    def __init__(self):
        self.use_intent_classification = False
        self.use_short_query_expansion = True
        self.short_query_word_threshold = 3
        self.short_query_expansion_cache = None
        self.short_query_expansion_cache_max = 64
        self.short_query_expansion_max_words = 12
        self.llm = _DummyLLM()

        self.use_infinity_embeddings = True
        self.vector_store_manager = None
        self.bm25_retriever = None
        self.retriever_k = 2
        self.sparse_rerank_limit = 2

    def get_infinity_embeddings(self):
        # Only needed for sparse re-rank; not used in these tests.
        return None


@pytest.mark.asyncio
async def test_prechecks_short_query_expands_via_vocab_without_llm():
    pipeline = _FakePipeline()
    node = make_prechecks_node(pipeline)

    state = await node({"raw_query": "MWEB", "metadata": {}, "effective_history_pairs": [], "is_dependent": False})

    assert pipeline.llm.calls == 0
    assert state["metadata"].get("short_query_expanded") is True
    assert state["metadata"].get("short_query_expand_source") == "vocab"
    assert state["metadata"].get("short_query_original") == "MWEB"
    rewritten = (state.get("rewritten_query") or "").lower()
    assert "mweb" in rewritten
    assert "mimblewimble" in rewritten
    assert state.get("retrieval_query") == state.get("rewritten_query")


@pytest.mark.asyncio
async def test_prechecks_unknown_short_query_calls_expand_llm():
    pipeline = _FakePipeline()
    pipeline.llm = _DummyLLM("What is xyzzy on the Litecoin network?")
    node = make_prechecks_node(pipeline)

    state = await node({"raw_query": "xyzzy", "metadata": {}, "effective_history_pairs": [], "is_dependent": False})

    assert pipeline.llm.calls == 1
    assert state["metadata"].get("short_query_expand_source") == "llm"
    assert "xyzzy" in (state.get("rewritten_query") or "").lower() or "litecoin" in (
        state.get("rewritten_query") or ""
    ).lower()


def test_expand_ltc_entities_is_idempotent():
    from backend.utils.litecoin_vocabulary import expand_ltc_entities

    once = expand_ltc_entities("charlie")
    twice = expand_ltc_entities(once)
    assert once == twice
    assert "lee" in once.lower() or "creator" in once.lower()


@pytest.mark.asyncio
async def test_retrieve_vector_results_not_filtered_by_score():
    # Distances: lower is better. We should keep the top K results returned by the store.
    d1 = Document(page_content="d1", metadata={"status": "published"})
    d2 = Document(page_content="d2", metadata={"status": "published"})
    d3 = Document(page_content="d3", metadata={"status": "published"})

    vector_results = [(d1, 0.01), (d2, 0.50), (d3, 1.00)]
    pipeline = _FakePipeline()
    pipeline.vector_store_manager = _DummyVectorStoreManager(_DummyVectorStore(vector_results))

    node = make_retrieve_node(pipeline)
    state = await node(
        {
            "retrieval_query": "mweb",
            "metadata": {},
            "query_vector": [0.0] * 1024,
            "query_sparse": None,
        }
    )

    assert [d.page_content for d in state["context_docs"]] == ["d1", "d2"]
    assert [d.page_content for d in state["published_sources"]] == ["d1", "d2"]


