import json
from unittest.mock import AsyncMock

from langchain_core.documents import Document


def _sources():
    return [
        Document(
            page_content="Litecoin was created by Charlie Lee.",
            metadata={
                "status": "published",
                "title": "Litecoin History",
                "payload_id": "art-1",
                "slug": "litecoin-history",
                "updated_at": "2026-03-01T00:00:00+00:00",
            },
        ),
        Document(
            page_content="Draft text must never reach the wire.",
            metadata={"status": "draft", "title": "Unpublished", "payload_id": "art-2"},
        ),
    ]


FOLLOW_UPS = [
    "When was Litecoin launched?",
    "How is Litecoin different from Bitcoin?",
]


SEEN_KWARGS: list = []


async def fake_astream_query(_query, _history, **kwargs):
    SEEN_KWARGS.append(kwargs)
    yield {"type": "sources", "sources": _sources()}
    yield {"type": "chunk", "content": "Litecoin was created by Charlie Lee."}
    yield {
        "type": "metadata",
        "metadata": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "duration_seconds": 0.01,
            "cache_hit": False,
            "cache_type": None,
        },
    }
    yield {"type": "complete", "from_cache": False}
    # Follow-ups are a second LLM call and trail `complete`.
    yield {"type": "follow_ups", "questions": FOLLOW_UPS}


def _patch_common(monkeypatch, main_module):
    monkeypatch.setattr(main_module, "check_rate_limit", AsyncMock(return_value=None))
    monkeypatch.setattr(main_module, "validate_and_consume_challenge", AsyncMock(return_value=None))
    monkeypatch.setattr(main_module, "is_turnstile_enabled", lambda: False)
    monkeypatch.setattr(main_module, "check_cost_based_throttling", AsyncMock(return_value=(False, None)))


def _sse_events(client, payload):
    headers = {"X-Fingerprint": "fp:testchallenge:testhash"}
    with client.stream("POST", "/api/v1/chat/stream", headers=headers, json=payload) as response:
        assert response.status_code == 200
        return [
            json.loads(line[6:])
            for line in response.iter_lines()
            if line and line.startswith("data: ")
        ]


def test_chat_stream_endpoint_emits_follow_ups_after_complete(client, monkeypatch):
    import backend.main as main_module

    class FakePipeline:
        astream_query = staticmethod(fake_astream_query)

    monkeypatch.setattr(main_module, "rag_pipeline_instance", FakePipeline())
    _patch_common(monkeypatch, main_module)
    monkeypatch.setattr(main_module.suggested_question_cache, "get", AsyncMock(return_value=None))

    SEEN_KWARGS.clear()
    sse_payloads = _sse_events(
        client, {"query": "What is Litecoin?", "chat_history": [], "category_hint": "cat-basics"}
    )
    # The landing-page topic is forwarded to the pipeline (logging / soft retrieval hint).
    assert SEEN_KWARGS and SEEN_KWARGS[0].get("category_hint") == "cat-basics"

    statuses = [event["status"] for event in sse_payloads]
    assert statuses == ["thinking", "sources", "streaming", "complete", "follow_ups"]

    # Source chips are structured metadata only: published docs, no chunk text.
    chips = sse_payloads[1]["sources"]
    assert [c["payload_id"] for c in chips] == ["art-1"]
    assert chips[0]["title"] == "Litecoin History"
    assert chips[0]["updated_at"] == "2026-03-01T00:00:00+00:00"
    assert "page_content" not in chips[0]
    assert "Draft text" not in json.dumps(sse_payloads)

    done = sse_payloads[3]
    assert done["fromCache"] is False
    assert done["isGrounded"] is False
    assert done["webSources"] == []
    assert done["abstained"] is False
    assert isinstance(done["requestId"], str) and len(done["requestId"]) >= 8

    # The trailing follow_ups event carries the same requestId so the client can
    # attach the chips to the already-finalized message.
    trailing = sse_payloads[-1]
    assert trailing["questions"] == FOLLOW_UPS
    assert trailing["requestId"] == done["requestId"]
    assert trailing["isComplete"] is True


def test_chat_stream_suggested_cache_hit_emits_follow_ups_after_complete(client, monkeypatch):
    """The suggested-question cache path in main.py must follow the same order."""
    import backend.main as main_module

    class FakePipeline:
        async def astream_query(self, *_a, **_k):  # pragma: no cover - must not be reached
            raise AssertionError("cache hit must not run the pipeline")
            yield  # unreachable on purpose: keeps this an async generator

        agenerate_follow_up_questions = AsyncMock(return_value=FOLLOW_UPS)

    monkeypatch.setattr(main_module, "rag_pipeline_instance", FakePipeline())
    _patch_common(monkeypatch, main_module)
    monkeypatch.setattr(
        main_module.suggested_question_cache,
        "get",
        AsyncMock(return_value=("Litecoin was created by Charlie Lee.", _sources())),
    )

    sse_payloads = _sse_events(client, {"query": "What is Litecoin?", "chat_history": []})
    statuses = [event["status"] for event in sse_payloads]
    assert statuses == ["thinking", "sources", "streaming", "complete", "follow_ups"]

    done = sse_payloads[3]
    assert done["fromCache"] == "suggested_question"
    assert sse_payloads[-1]["questions"] == FOLLOW_UPS
    assert sse_payloads[-1]["requestId"] == done["requestId"]
