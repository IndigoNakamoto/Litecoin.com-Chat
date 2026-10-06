"""
Phase 0 freshness fixes:

- Redis vector cache entries carry a TTL, an `is_grounded` flag, and the
  Payload ids they cite.
- CMS webhook invalidates every cache layer that cited the changed article.
- Semantic cache graph node replays `is_grounded` on a hit.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from backend.cache_utils import QueryCache, SemanticCache
from backend.services.redis_vector_cache import (
    CacheEntry,
    RedisVectorCache,
    _payload_ids_from_sources,
)


def _src(payload_id: str, status: str = "published") -> Dict[str, Any]:
    return {"page_content": "x", "metadata": {"payload_id": payload_id, "status": status}}


class _FakeAsyncRedis:
    """Minimal async Redis stand-in for hash + scan + expire."""

    def __init__(self):
        self.hashes: Dict[str, Dict[str, bytes]] = {}
        self.expires: Dict[str, int] = {}

    async def ping(self):
        return True

    async def hset(self, key, mapping):
        self.hashes[key] = dict(mapping)

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

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


def _cache_with_fake_client(ttl: int = 600) -> RedisVectorCache:
    cache = RedisVectorCache(redis_url="redis://unused", ttl_seconds=ttl)
    fake = _FakeAsyncRedis()
    cache._client = fake
    cache._index_created = True
    cache._ensure_index = AsyncMock()  # type: ignore[assignment]
    return cache


def test_payload_ids_from_sources_dedupes_and_skips_missing():
    ids = _payload_ids_from_sources([_src("a"), _src("b"), _src("a"), {"metadata": {}}, "junk"])
    assert ids == ["a", "b"]


@pytest.mark.asyncio
async def test_redis_set_stores_ttl_grounded_flag_and_payload_ids():
    cache = _cache_with_fake_client(ttl=123)
    vec = [0.1, 0.2, 0.3]
    ok = await cache.set(vec, "q", "answer", [_src("doc1"), _src("doc2")], is_grounded=True)
    assert ok

    key = cache._generate_key(vec)
    stored = cache._client.hashes[key]
    assert stored["is_grounded"] == b"1"
    assert stored["payload_ids"] == b"doc1 doc2"
    assert cache._client.expires[key] == 123


@pytest.mark.asyncio
async def test_redis_set_no_ttl_when_disabled():
    cache = _cache_with_fake_client(ttl=0)
    vec = [0.5, 0.5]
    await cache.set(vec, "q", "a", [], is_grounded=False)
    assert cache._client.expires == {}
    assert cache._client.hashes[cache._generate_key(vec)]["is_grounded"] == b"0"


@pytest.mark.asyncio
async def test_redis_invalidate_by_payload_id_removes_only_citing_entries():
    cache = _cache_with_fake_client()
    await cache.set([1.0, 0.0], "q1", "a1", [_src("keep")])
    await cache.set([0.0, 1.0], "q2", "a2", [_src("gone"), _src("keep")])
    await cache.set([1.0, 1.0], "q3", "a3", [_src("gone")])

    removed = await cache.invalidate_by_payload_id("gone")
    assert removed == 2
    remaining = list(cache._client.hashes.values())
    assert len(remaining) == 1
    assert remaining[0]["payload_ids"] == b"keep"

    assert await cache.invalidate_by_payload_id("") == 0


@pytest.mark.asyncio
async def test_redis_get_delegates_to_get_entry():
    cache = _cache_with_fake_client()
    cache.get_entry = AsyncMock(  # type: ignore[assignment]
        return_value=CacheEntry(query="q", response="r", sources=[_src("x")], similarity=0.99, is_grounded=True)
    )
    result = await cache.get([0.1])
    assert result == ("r", [_src("x")])


def test_query_cache_invalidate_by_payload_id():
    qc = QueryCache()
    qc.set("what is mweb", [], "ans", [Document(page_content="a", metadata={"payload_id": "p1"})])
    qc.set("what is ltc", [], "ans", [Document(page_content="b", metadata={"payload_id": "p2"})])
    assert qc.invalidate_by_payload_id("p1") == 1
    assert qc.get("what is mweb", []) is None
    assert qc.get("what is ltc", []) is not None


def test_semantic_cache_invalidate_by_payload_id():
    class _Emb:
        def embed_query(self, text):
            return [1.0, 0.0] if "mweb" in text else [0.0, 1.0]

    sc = SemanticCache(_Emb(), threshold=0.9)
    sc.set("what is mweb", [], "ans", [Document(page_content="a", metadata={"payload_id": "p1"})])
    sc.set("what is ltc", [], "ans", [Document(page_content="b", metadata={"payload_id": "p2"})])
    assert sc.invalidate_by_payload_id("p1") == 1
    assert sc.get("what is mweb", []) is None
    assert sc.get("what is ltc", []) is not None


@pytest.mark.asyncio
async def test_webhook_helper_invalidates_every_cache_layer():
    from backend.api.v1.sync import payload as sync_payload

    redis_cache = MagicMock()
    redis_cache.invalidate_by_payload_id = AsyncMock(return_value=2)
    legacy = MagicMock()
    legacy.invalidate_by_payload_id = MagicMock(return_value=1)
    qc = MagicMock()
    qc.invalidate_by_payload_id = MagicMock(return_value=3)
    exact = MagicMock()
    exact.invalidate_by_payload_id = AsyncMock(return_value=4)

    pipeline = MagicMock()
    pipeline.get_redis_vector_cache = MagicMock(return_value=redis_cache)
    pipeline.get_exact_answer_cache = MagicMock(return_value=exact)
    pipeline.semantic_cache = legacy
    pipeline.query_cache = qc

    previous = sync_payload._global_rag_pipeline
    sync_payload.set_global_rag_pipeline(pipeline)
    try:
        removed = await sync_payload.invalidate_cached_answers_for("doc-7")
    finally:
        sync_payload._global_rag_pipeline = previous

    assert removed == 10
    redis_cache.invalidate_by_payload_id.assert_awaited_once_with("doc-7")
    legacy.invalidate_by_payload_id.assert_called_once_with("doc-7")
    qc.invalidate_by_payload_id.assert_called_once_with("doc-7")
    exact.invalidate_by_payload_id.assert_awaited_once_with("doc-7")


@pytest.mark.asyncio
async def test_webhook_helper_survives_cache_errors():
    from backend.api.v1.sync import payload as sync_payload

    pipeline = MagicMock()
    pipeline.get_redis_vector_cache = MagicMock(side_effect=RuntimeError("boom"))
    previous = sync_payload._global_rag_pipeline
    sync_payload.set_global_rag_pipeline(pipeline)
    try:
        assert await sync_payload.invalidate_cached_answers_for("doc") == 0
    finally:
        sync_payload._global_rag_pipeline = previous


@pytest.mark.asyncio
async def test_semantic_cache_node_replays_is_grounded():
    from backend.rag_graph.nodes.semantic_cache import make_semantic_cache_node

    class _Infinity:
        dimension = 2

        async def embed_query(self, text):
            return [0.1, 0.2], None

    class _RedisCache:
        async def get_entry(self, vec, query_text=None):
            return CacheEntry(
                query="q",
                response="cached",
                sources=[_src("p1")],
                similarity=0.99,
                is_grounded=True,
            )

    pipeline = MagicMock()
    pipeline.use_redis_cache = True
    pipeline.use_infinity_embeddings = True
    pipeline.get_infinity_embeddings = lambda: _Infinity()
    pipeline.get_redis_vector_cache = lambda: _RedisCache()
    pipeline.semantic_cache = None

    node = make_semantic_cache_node(pipeline)
    state: Dict[str, Any] = {"rewritten_query": "q", "metadata": {}}
    out = await node(state)  # type: ignore[arg-type]

    assert out["early_answer"] == "cached"
    assert out["early_cache_type"] == "redis_vector"
    assert out["metadata"]["is_grounded"] is True
    assert out["early_sources"][0].metadata["payload_id"] == "p1"


_LDK_QUESTIONS = (
    "What is the role of MwebCoinDatabase in the Litecoin Dev Kit architecture?",
    "What cryptographic libraries does the Litecoin Dev Kit use for MWEB?",
    "What features are included in the Litecoin Dev Kit prototype?",
)

# Written when entity matching was a substring check, so MwebCoinDatabase
# also picked up the MWEB bag. Still in Redis until those keys expire.
_LDK_ARCHITECTURE_STORED_BEFORE_WORD_BOUNDARY = (
    "What is the role of MwebCoinDatabase in the Litecoin Dev Kit architecture? "
    "mimblewimble extension blocks privacy confidential transactions lip-0002 lip-0003 "
    "ldk bitcoin bdk port descriptor wallet library peg-in peg-out rust uniffi bindings prototype"
)


def test_cache_question_guard_accepts_same_question_and_one_token_paraphrase():
    from backend.utils.litecoin_vocabulary import expand_ltc_entities, normalize_ltc_keywords

    from backend.services.redis_vector_cache import same_cached_question

    question = _LDK_QUESTIONS[0]
    normalized = normalize_ltc_keywords(question)
    expanded = expand_ltc_entities(normalized)
    assert expanded != normalized
    assert same_cached_question(normalized, expanded)
    assert same_cached_question(normalized, _LDK_ARCHITECTURE_STORED_BEFORE_WORD_BOUNDARY)
    assert same_cached_question(
        "what is the litecoin dev kit",
        "what is the litecoin dev kit exactly",
    )
    assert same_cached_question("what is litecoin dev kit", "what is the litecoin dev kit")


def test_cache_question_guard_rejects_distinct_ldk_questions():
    from backend.utils.litecoin_vocabulary import expand_ltc_entities, normalize_ltc_keywords

    from backend.services.redis_vector_cache import same_cached_question

    normalized = [normalize_ltc_keywords(q) for q in _LDK_QUESTIONS]
    stored = [expand_ltc_entities(q) for q in normalized]
    stored[0] = _LDK_ARCHITECTURE_STORED_BEFORE_WORD_BOUNDARY

    for i, lookup in enumerate(normalized):
        for j, entry in enumerate(stored):
            if i == j:
                assert same_cached_question(lookup, entry)
            else:
                assert not same_cached_question(lookup, entry)
