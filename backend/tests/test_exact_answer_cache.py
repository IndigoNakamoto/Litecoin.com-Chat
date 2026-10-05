"""
Exact normalised-text answer cache: the no-embedding tier in front of the
semantic cache for empty-history questions.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from backend.services.exact_answer_cache import ExactAnswerCache, KEY_PREFIX, normalize_question


class _FakeAsyncRedis:
    def __init__(self):
        self.hashes: Dict[str, Dict[str, Any]] = {}
        self.expires: Dict[str, int] = {}

    async def hset(self, key, mapping):
        self.hashes[key] = dict(mapping)

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def expire(self, key, ttl):
        self.expires[key] = ttl

    async def delete(self, *keys):
        for k in keys:
            self.hashes.pop(k, None)
            self.expires.pop(k, None)

    async def scan_iter(self, match=None):
        prefix = (match or "*").rstrip("*")
        for k in list(self.hashes.keys()):
            if k.startswith(prefix):
                yield k


def _cache(ttl: int = 600) -> ExactAnswerCache:
    c = ExactAnswerCache(ttl_seconds=ttl)
    c._client = _FakeAsyncRedis()
    return c


def _src(pid: str) -> Dict[str, Any]:
    return {"page_content": "x", "metadata": {"payload_id": pid, "status": "published"}}


def test_normalize_question_collapses_case_space_and_trailing_punctuation():
    assert normalize_question("  What is   MWEB?? ") == "what is mweb"
    assert normalize_question("what is mweb") == normalize_question("What Is MWEB.")
    assert ExactAnswerCache.key_for("What is MWEB?") == ExactAnswerCache.key_for("what is mweb")
    assert ExactAnswerCache.key_for("a").startswith(KEY_PREFIX)


@pytest.mark.asyncio
async def test_set_then_get_roundtrip_with_grounded_flag_ttl_and_payload_ids():
    c = _cache(ttl=321)
    assert await c.set("What is MWEB?", "answer", [_src("p1"), _src("p2"), _src("p1")], is_grounded=True)
    key = ExactAnswerCache.key_for("what is mweb")
    assert c._client.hashes[key]["payload_ids"] == "p1 p2"
    assert c._client.expires[key] == 321

    entry = await c.get("  what is MWEB ")
    assert entry is not None
    assert entry.answer == "answer"
    assert entry.is_grounded is True
    assert [s["metadata"]["payload_id"] for s in entry.sources] == ["p1", "p2", "p1"]
    assert await c.get("something else") is None


@pytest.mark.asyncio
async def test_set_rejects_empty_question_or_answer():
    c = _cache()
    assert await c.set("   ", "answer", []) is False
    assert await c.set("q", "   ", []) is False
    assert c._client.hashes == {}


@pytest.mark.asyncio
async def test_invalidate_by_payload_id_and_clear():
    c = _cache()
    await c.set("q1", "a1", [_src("keep")])
    await c.set("q2", "a2", [_src("gone"), _src("keep")])
    await c.set("q3", "a3", [_src("gone")])
    assert await c.invalidate_by_payload_id("gone") == 2
    assert len(c._client.hashes) == 1
    assert await c.invalidate_by_payload_id("") == 0
    assert (await c.stats())["entries"] == 1
    assert await c.clear() == 1
    assert c._client.hashes == {}


@pytest.mark.asyncio
async def test_semantic_cache_node_hits_exact_cache_before_embedding():
    from backend.rag_graph.nodes.semantic_cache import make_semantic_cache_node

    c = _cache()
    await c.set("What is MWEB?", "exact answer", [_src("p9")], is_grounded=False)

    infinity = MagicMock()
    infinity.embed_query = AsyncMock(return_value=([0.1], None))

    pipeline = MagicMock()
    pipeline.use_exact_answer_cache = True
    pipeline.use_redis_cache = True
    pipeline.use_infinity_embeddings = True
    pipeline.get_exact_answer_cache = lambda: c
    pipeline.get_infinity_embeddings = lambda: infinity
    pipeline.semantic_cache = None

    node = make_semantic_cache_node(pipeline)
    state: Dict[str, Any] = {"raw_query": "what is mweb", "sanitized_query": "what is mweb", "chat_history_pairs": [], "metadata": {}}
    out = await node(state)  # type: ignore[arg-type]

    assert out["early_answer"] == "exact answer"
    assert out["early_cache_type"] == "exact_redis"
    assert out["metadata"]["cache_type"] == "exact_redis"
    assert out["early_sources"][0].metadata["payload_id"] == "p9"
    infinity.embed_query.assert_not_awaited()  # no embedding on an exact hit


@pytest.mark.asyncio
async def test_semantic_cache_node_skips_exact_cache_when_history_present():
    from backend.rag_graph.nodes.semantic_cache import make_semantic_cache_node

    c = _cache()
    await c.set("what is it", "stale", [])

    infinity = MagicMock()
    infinity.embed_query = AsyncMock(return_value=([0.1], None))
    redis_cache = MagicMock()
    redis_cache.get_entry = AsyncMock(return_value=None)

    pipeline = MagicMock()
    pipeline.use_exact_answer_cache = True
    pipeline.use_redis_cache = True
    pipeline.use_infinity_embeddings = True
    pipeline.get_exact_answer_cache = lambda: c
    pipeline.get_infinity_embeddings = lambda: infinity
    pipeline.get_redis_vector_cache = lambda: redis_cache
    pipeline.semantic_cache = None

    node = make_semantic_cache_node(pipeline)
    state: Dict[str, Any] = {
        "raw_query": "what is it", "sanitized_query": "what is it",
        "chat_history_pairs": [("What is MWEB?", "MWEB is ...")], "rewritten_query": "what is mweb", "metadata": {},
    }
    out = await node(state)  # type: ignore[arg-type]
    assert out.get("early_answer") is None
    infinity.embed_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_exact_answer_only_for_empty_history_grounded_kb_answers():
    from backend.rag_pipeline import RAGPipeline

    c = _cache()
    p = object.__new__(RAGPipeline)
    p.use_exact_answer_cache = True
    p.get_exact_answer_cache = lambda: c
    docs = [Document(page_content="a", metadata={"payload_id": "p1", "status": "published"})]

    # history -> skip
    await p._store_exact_answer({"sanitized_query": "q", "chat_history_pairs": [("a", "b")]}, "ans", docs, False, False)
    # kb insufficient -> skip
    await p._store_exact_answer({"sanitized_query": "q", "chat_history_pairs": []}, "ans", docs, False, True)
    assert c._client.hashes == {}

    await p._store_exact_answer({"sanitized_query": "What is MWEB?", "chat_history_pairs": []}, "ans", docs, True, False)
    entry = await c.get("what is mweb")
    assert entry is not None and entry.answer == "ans" and entry.is_grounded is True
    assert entry.sources[0]["metadata"]["payload_id"] == "p1"
