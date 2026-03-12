import json
from unittest.mock import AsyncMock

from langchain_core.documents import Document


async def fake_astream_query(_query, _history):
    sources = [
        Document(
            page_content="Litecoin was created by Charlie Lee.",
            metadata={"status": "published", "title": "Litecoin History"},
        )
    ]
    yield {"type": "sources", "sources": sources}
    yield {"type": "chunk", "content": "Litecoin was created by Charlie Lee."}
    yield {
        "type": "follow_ups",
        "questions": [
            "When was Litecoin launched?",
            "How is Litecoin different from Bitcoin?",
        ],
    }
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


def test_chat_stream_endpoint_emits_follow_up_sse_event(client, monkeypatch):
    import backend.main as main_module

    class FakePipeline:
        astream_query = staticmethod(fake_astream_query)

    monkeypatch.setattr(main_module, "rag_pipeline_instance", FakePipeline())
    monkeypatch.setattr(main_module, "check_rate_limit", AsyncMock(return_value=None))
    monkeypatch.setattr(main_module, "validate_and_consume_challenge", AsyncMock(return_value=None))
    monkeypatch.setattr(main_module, "is_turnstile_enabled", lambda: False)
    monkeypatch.setattr(main_module, "check_cost_based_throttling", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(main_module.suggested_question_cache, "get", AsyncMock(return_value=None))

    headers = {"X-Fingerprint": "fp:testchallenge:testhash"}
    payload = {"query": "What is Litecoin?", "chat_history": []}

    with client.stream("POST", "/api/v1/chat/stream", headers=headers, json=payload) as response:
        assert response.status_code == 200
        sse_payloads = [
            json.loads(line[6:])
            for line in response.iter_lines()
            if line and line.startswith("data: ")
        ]

    statuses = [event["status"] for event in sse_payloads]
    assert statuses == ["thinking", "sources", "streaming", "follow_ups", "complete"]
    assert sse_payloads[3]["questions"] == [
        "When was Litecoin launched?",
        "How is Litecoin different from Bitcoin?",
    ]
    assert sse_payloads[-1]["fromCache"] is False
