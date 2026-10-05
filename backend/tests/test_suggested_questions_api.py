"""
GET /api/v1/suggested-questions — landing-page data (categories + questions +
`cached` flags) served through the backend instead of the browser calling
Payload directly.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

import backend.api.v1.suggested_questions as sq


class _Resp:
    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeHttpClient:
    """Stands in for httpx.AsyncClient; routes by URL suffix."""

    responses: Dict[str, _Resp] = {}
    calls: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, **k):
        _FakeHttpClient.calls.append((url, dict(params or {})))
        for suffix, resp in _FakeHttpClient.responses.items():
            if url.endswith(suffix):
                return resp
        return _Resp(404, {})


CATEGORIES = [
    {"id": "cat-basics", "name": "Basics", "description": "Start here", "icon": "🪙", "audienceLevel": "beginner", "order": 1, "parent": None},
    {"id": "cat-mweb", "name": {"en": "MWEB", "es": "MWEB (es)"}, "order": 2, "parent": None},
    {"id": "cat-sub", "name": "Sub", "order": 3, "parent": "cat-basics"},
]
QUESTIONS = [
    {"id": "q1", "question": "What is Litecoin?", "order": 2, "isActive": True, "category": "cat-basics"},
    {"id": "q2", "question": "What is MWEB?", "order": 1, "isActive": True, "category": {"id": "cat-mweb", "name": "MWEB"}},
    {"id": "q3", "question": "Old question", "order": 3, "isActive": False, "category": None},
    {"id": "q4", "question": "Uncategorised but active", "order": 4, "isActive": True},
]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    sq.invalidate()
    _FakeHttpClient.calls = []
    _FakeHttpClient.responses = {
        "/api/suggested-questions": _Resp(200, {"docs": QUESTIONS}),
        "/api/categories": _Resp(200, {"docs": CATEGORIES}),
    }
    monkeypatch.setattr(sq.httpx, "AsyncClient", _FakeHttpClient)
    monkeypatch.setattr(sq, "check_rate_limit", AsyncMock(return_value=None))
    yield
    sq.invalidate()


def _patch_cache(monkeypatch, cached: Dict[str, bool]):
    from backend.cache_utils import suggested_question_cache

    monkeypatch.setattr(suggested_question_cache, "cached_flags", AsyncMock(return_value=cached))


def test_returns_categories_questions_and_cached_flags(client, monkeypatch):
    _patch_cache(monkeypatch, {"What is MWEB?": True})

    r = client.get("/api/v1/suggested-questions")
    assert r.status_code == 200
    body = r.json()
    assert body["fallback"] is False

    # Questions sorted by order, inactive ones kept but flagged, relationship normalised to an id
    qs = body["questions"]
    assert [q["id"] for q in qs] == ["q2", "q1", "q3", "q4"]
    by_id = {q["id"]: q for q in qs}
    assert by_id["q2"]["categoryId"] == "cat-mweb" and by_id["q2"]["cached"] is True
    assert by_id["q1"]["categoryId"] == "cat-basics" and by_id["q1"]["cached"] is False
    assert by_id["q3"]["isActive"] is False and by_id["q3"]["categoryId"] is None
    assert by_id["q4"]["categoryId"] is None

    # Categories carry display metadata, parent and the count of *active* questions
    cats = {c["id"]: c for c in body["categories"]}
    assert cats["cat-basics"]["icon"] == "🪙"
    assert cats["cat-basics"]["audienceLevel"] == "beginner"
    assert cats["cat-basics"]["questionCount"] == 1
    assert cats["cat-mweb"]["name"] == "MWEB"  # localized object -> en
    assert cats["cat-mweb"]["questionCount"] == 1
    assert cats["cat-sub"]["parentId"] == "cat-basics"
    assert cats["cat-sub"]["questionCount"] == 0
    assert r.headers["cache-control"].startswith("public")


def test_category_filter_and_locale_forwarding(client, monkeypatch):
    _patch_cache(monkeypatch, {})

    r = client.get("/api/v1/suggested-questions", params={"category": "cat-basics", "locale": "es"})
    assert r.status_code == 200
    body = r.json()
    assert [q["id"] for q in body["questions"]] == ["q1"]
    # categories list is unfiltered so the picker can still navigate
    assert len(body["categories"]) == 3
    # locale forwarded to Payload; unknown locales fall back to en
    assert all(p.get("locale") == "es" for _, p in _FakeHttpClient.calls)

    _FakeHttpClient.calls = []
    client.get("/api/v1/suggested-questions", params={"locale": "xx"})
    assert all(p.get("locale") == "en" for _, p in _FakeHttpClient.calls)


def test_in_process_cache_avoids_refetching_cms(client, monkeypatch):
    _patch_cache(monkeypatch, {})
    client.get("/api/v1/suggested-questions")
    client.get("/api/v1/suggested-questions")
    # two requests, one CMS round (questions + categories)
    assert len(_FakeHttpClient.calls) == 2


def test_categories_unavailable_still_serves_questions(client, monkeypatch):
    _patch_cache(monkeypatch, {})
    _FakeHttpClient.responses["/api/categories"] = _Resp(500, {})
    r = client.get("/api/v1/suggested-questions")
    assert r.status_code == 200
    assert r.json()["categories"] == []
    assert len(r.json()["questions"]) == 4


def test_cms_down_is_503(client, monkeypatch):
    _patch_cache(monkeypatch, {})

    class _Boom(_FakeHttpClient):
        async def get(self, *a, **k):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(sq.httpx, "AsyncClient", _Boom)
    r = client.get("/api/v1/suggested-questions")
    assert r.status_code == 503


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("6718f0c2a1b2c3d4e5f60718", "6718f0c2a1b2c3d4e5f60718"),
        ("  cat-basics ", "cat-basics"),
        ("", None),
        ("   ", None),
        ("$where: 1", None),  # NoSQL-looking junk is dropped, not raised
        ("x" * 65, None),
        (None, None),
    ],
)
def test_chat_request_category_hint_is_sanitised(raw, expected):
    from backend.data_models import ChatRequest

    req = ChatRequest(query="What is Litecoin?", chat_history=[], category_hint=raw)
    assert req.category_hint == expected


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"cache_type": None, "intent": None}, True),                               # normal KB answer
        ({"cache_type": "exact_redis"}, True),                                       # cache hit replay is still a KB answer
        ({"cache_type": "blockchain_lookup", "intent": "blockchain_lookup"}, False),  # live card: never pre-cache
        ({"cache_type": "blockchain_lookup_error", "intent": "blockchain_lookup"}, False),
        ({"early_cache_type": "blockchain_lookup"}, False),
        ({"cache_type": "intent_refuse"}, False),
        ({"early_cache_type": "intent_escalate"}, False),
        ({"cache_type": "incident_pin"}, False),
        ({"abstained": True}, False),
        ({"tool_unavailable": "gemini"}, False),
        (None, True),
    ],
)
def test_is_precacheable_answer(metadata, expected):
    from backend.main import is_precacheable_answer

    assert is_precacheable_answer(metadata) is expected


@pytest.mark.asyncio
async def test_suggested_question_cache_cached_flags_pipelines_exists():
    from backend.cache_utils import SuggestedQuestionCache

    class _Pipe:
        def __init__(self):
            self.keys = []

        def exists(self, key):
            self.keys.append(key)

        async def execute(self):
            return [1 if "a" in k else 0 for k in self.keys]

    class _Redis:
        def pipeline(self):
            return _Pipe()

    c = SuggestedQuestionCache()
    c._redis_client = _Redis()
    # Keys are md5 of the normalised text, so we can't predict "a" in key reliably;
    # just check the shape and that a result is produced per question.
    flags = await c.cached_flags(["What is MWEB?", "What is Litecoin?"])
    assert set(flags) == {"What is MWEB?", "What is Litecoin?"}
    assert all(isinstance(v, bool) for v in flags.values())
    assert await c.cached_flags([]) == {}


@pytest.mark.asyncio
async def test_fetch_suggested_questions_active_only_uses_bracket_where_and_filters(monkeypatch):
    """Payload 3 ignores a JSON-string `where`; the warm-up must never see inactive rows."""
    import backend.utils.suggested_questions as usq

    seen: Dict[str, Any] = {}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None):
            seen["url"], seen["params"] = url, dict(params or {})
            # Emulate a server that ignored the filter and returned everything.
            body = {"docs": [
                {"id": "1", "question": "Active one", "isActive": True},
                {"id": "2", "question": "Inactive one", "isActive": False},
                {"id": "3", "question": "Legacy row without flag"},
            ]}
            r = _Resp(200, body)
            r.raise_for_status = lambda: None
            return r

    monkeypatch.setattr(usq.httpx, "AsyncClient", _Client)

    active = await usq.fetch_suggested_questions(payload_url="http://cms", active_only=True)
    assert seen["url"] == "http://cms/api/suggested-questions"
    assert seen["params"]["where[isActive][equals]"] == "true" and "where" not in seen["params"]
    assert [q["id"] for q in active] == ["1", "3"]

    everything = await usq.fetch_suggested_questions(payload_url="http://cms", active_only=False)
    assert "where[isActive][equals]" not in seen["params"]
    assert [q["id"] for q in everything] == ["1", "2", "3"]
