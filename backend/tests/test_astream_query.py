from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from backend.rag_pipeline import RAGPipeline


class DummyGraph:
    def __init__(self, state):
        self.state = state

    async def ainvoke(self, _payload):
        return self.state


class DummyChain:
    def __init__(self, chunks):
        self.chunks = chunks

    async def astream(self, _payload):
        for chunk in self.chunks:
            yield chunk


def make_pipeline(state, chunks=None, follow_ups=None):
    pipeline = object.__new__(RAGPipeline)
    pipeline._get_rag_graph = lambda: DummyGraph(state)
    pipeline._select_document_chain = lambda _state: (DummyChain(chunks or []), "simple", "test instruction")
    pipeline.query_cache = MagicMock()
    pipeline.query_cache.set = MagicMock()
    pipeline.use_redis_cache = False
    pipeline.semantic_cache = None
    pipeline.get_redis_vector_cache = MagicMock(return_value=None)
    pipeline.monitoring_enabled = False
    pipeline.generic_user_error_message = "Generic error"
    pipeline.no_kb_match_response = "No KB response"
    pipeline.agenerate_follow_up_questions = AsyncMock(return_value=follow_ups or [])
    pipeline.track_llm_metrics = MagicMock()
    pipeline.estimate_gemini_cost = MagicMock(return_value=0.0)
    pipeline.record_spend = AsyncMock(return_value={})
    pipeline.model_name = "test-model"
    return pipeline


@pytest.mark.asyncio
async def test_astream_query_emits_follow_ups_before_complete():
    sources = [
        Document(
            page_content="Litecoin was created by Charlie Lee in 2011.",
            metadata={"status": "published", "title": "Litecoin History"},
        )
    ]
    state = {
        "metadata": {},
        "context_docs": sources,
        "published_sources": sources,
        "retrieval_failed": False,
        "converted_history_messages": [],
        "sanitized_query": "What is Litecoin?",
        "complexity_route": "simple",
    }
    pipeline = make_pipeline(
        state,
        chunks=["Litecoin ", "is a cryptocurrency."],
        follow_ups=["How is Litecoin different from Bitcoin?", "Who created Litecoin?"],
    )

    events = [event async for event in pipeline.astream_query("What is Litecoin?", [])]
    event_types = [event["type"] for event in events]

    assert event_types == ["sources", "chunk", "chunk", "follow_ups", "metadata", "complete"]
    assert events[3]["questions"] == [
        "How is Litecoin different from Bitcoin?",
        "Who created Litecoin?",
    ]
    assert events[-1]["from_cache"] is False
    pipeline.agenerate_follow_up_questions.assert_awaited_once()
    pipeline.query_cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_astream_query_emits_follow_ups_for_early_answer_cache_path():
    sources = [
        Document(
            page_content="Litecoin launched in 2011.",
            metadata={"status": "published", "title": "Launch"},
        )
    ]
    state = {
        "metadata": {},
        "early_answer": "Cached answer",
        "early_sources": sources,
    }
    pipeline = make_pipeline(
        state,
        follow_ups=["When was Litecoin launched?", "What problem was it designed to solve?"],
    )

    events = [event async for event in pipeline.astream_query("What is Litecoin?", [])]
    event_types = [event["type"] for event in events]
    follow_up_index = event_types.index("follow_ups")
    metadata_index = event_types.index("metadata")
    complete_index = event_types.index("complete")

    assert follow_up_index < metadata_index < complete_index
    assert events[follow_up_index]["questions"] == [
        "When was Litecoin launched?",
        "What problem was it designed to solve?",
    ]
    assert events[complete_index]["from_cache"] is True
    pipeline.agenerate_follow_up_questions.assert_awaited_once()


@pytest.mark.asyncio
async def test_astream_query_omits_follow_ups_when_no_sources():
    state = {
        "metadata": {},
        "context_docs": [],
        "published_sources": [],
        "retrieval_failed": False,
    }
    pipeline = make_pipeline(
        state,
        follow_ups=["This should never be emitted?"],
    )

    events = [event async for event in pipeline.astream_query("Unknown query", [])]
    event_types = [event["type"] for event in events]

    assert event_types == ["sources", "chunk", "metadata", "complete"]
    assert "follow_ups" not in event_types
    pipeline.agenerate_follow_up_questions.assert_not_awaited()
