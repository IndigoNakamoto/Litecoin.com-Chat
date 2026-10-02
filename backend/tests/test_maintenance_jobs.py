"""Scheduled maintenance jobs: stale-doc report, gap clustering, reconcile, doc-source registry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from backend.jobs import maintenance as mj


# --------------------------------------------------------------------------- async Mongo fake


class _Cursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def sort(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, docs=None, agg=None):
        self.docs = docs or []
        self.agg = agg or []
        self.inserted: List[Dict[str, Any]] = []
        self.updates: List[Any] = []

    def aggregate(self, _pipeline):
        return _Cursor(self.agg)

    def find(self, *_a, **_k):
        return _Cursor(self.docs)

    async def insert_one(self, doc):
        self.inserted.append(doc)

    async def update_one(self, sel, upd):
        self.updates.append(("one", sel, upd))

    async def update_many(self, sel, upd):
        self.updates.append(("many", sel, upd))


class _DB(dict):
    def __getitem__(self, name):
        if name not in self:
            dict.__setitem__(self, name, _Coll())
        return dict.__getitem__(self, name)


@pytest.fixture
def no_alerts(monkeypatch):
    sent: List[Dict[str, Any]] = []

    async def _fake_alert(title, description, level="info", fields=None):
        sent.append({"title": title, "level": level, "fields": fields or []})

    monkeypatch.setattr(mj, "_alert", _fake_alert)
    return sent


# --------------------------------------------------------------------------- stale report


@pytest.mark.asyncio
async def test_flag_stale_articles_flags_past_window_only(monkeypatch, no_alerts):
    now = datetime.now(timezone.utc)
    agg = [
        {"_id": "old", "title": "Old", "slug": "old", "updated_at": now - timedelta(days=400), "last_reviewed_at": None, "review_interval_days": 180, "source_tier": "cms"},
        {"_id": "fresh", "title": "Fresh", "slug": "fresh", "updated_at": now - timedelta(days=5), "last_reviewed_at": None, "review_interval_days": 180},
        {"_id": "reviewed", "title": "Reviewed", "slug": "r", "updated_at": now - timedelta(days=400), "last_reviewed_at": now - timedelta(days=10), "review_interval_days": 180},
        {"_id": "nowindow", "title": "NoWindow", "slug": "n", "updated_at": now - timedelta(days=900), "last_reviewed_at": None, "review_interval_days": 0},
        {"_id": "default", "title": "Default", "slug": "d", "updated_at": now - timedelta(days=200), "last_reviewed_at": None, "review_interval_days": None},
    ]
    db = _DB()
    db["litecoin_docs"] = _Coll(agg=agg)
    db["answer_feedback"] = _Coll(agg=[{"_id": "old", "n": 3}])
    monkeypatch.setattr(mj, "_mongo_db", AsyncMock(return_value=db))
    monkeypatch.setenv("MONGO_COLLECTION_NAME", "litecoin_docs")

    summary = await mj._flag_stale_articles("run1")
    assert summary["total_published"] == 5
    assert summary["stale_count"] == 2
    assert summary["top"] == ["Old", "Default"]

    report = db["stale_doc_reports"].inserted[0]
    by_id = {s["payload_id"]: s for s in report["stale"]}
    assert by_id["old"]["thumbs_down_30d"] == 3
    assert by_id["default"]["review_interval_days"] == mj.STALE_DEFAULT_INTERVAL_DAYS
    assert no_alerts and no_alerts[0]["level"] == "warning"


@pytest.mark.asyncio
async def test_flag_stale_articles_silent_when_nothing_stale(monkeypatch, no_alerts):
    now = datetime.now(timezone.utc)
    db = _DB()
    db["litecoin_docs"] = _Coll(agg=[{"_id": "a", "title": "A", "updated_at": now, "review_interval_days": 30}])
    monkeypatch.setattr(mj, "_mongo_db", AsyncMock(return_value=db))
    summary = await mj._flag_stale_articles("run2")
    assert summary["stale_count"] == 0
    assert no_alerts == []


# --------------------------------------------------------------------------- clustering


@pytest.mark.asyncio
async def test_cluster_gap_candidates_merges_and_drafts(monkeypatch, no_alerts):
    pending = [
        {"_id": "c1", "user_question": "What is LitVM on Litecoin?", "question_embedding": [1.0, 0.0], "question_frequency": 1, "generated_answer": "LitVM is ...", "topic_cluster": "litvm", "grounding_sources": [{"url": "https://x"}]},
        {"_id": "c2", "user_question": "Explain LitVM please", "question_embedding": [0.99, 0.05], "question_frequency": 1, "generated_answer": "short"},
        {"_id": "c3", "user_question": "How do I accept LTC in Shopify?", "question_embedding": [0.0, 1.0], "question_frequency": 1, "generated_answer": "..."},
    ]
    coll = _Coll(docs=pending)
    monkeypatch.setattr("backend.dependencies.get_knowledge_candidates_collection", AsyncMock(return_value=coll))
    monkeypatch.setattr(mj, "GAP_CLUSTER_MIN_FREQUENCY", 2)
    created: List[Dict[str, Any]] = []

    async def _fake_draft(**kw):
        created.append(kw)
        return "article-123"

    monkeypatch.setattr("backend.services.article_draft_generator.create_payload_draft", _fake_draft)

    summary = await mj._cluster_gap_candidates("run3")
    assert summary["clusters"] == 2
    assert summary["merged"] == 1
    assert summary["drafted"] == 1
    assert created[0]["publish_status"] == "draft"
    assert "Explain LitVM please" in created[0]["answer"]

    kinds = [u[0] for u in coll.updates]
    assert "many" in kinds  # c2 merged into c1
    merged_update = next(u for u in coll.updates if u[0] == "many")
    assert merged_update[2]["$set"]["status"] == "merged"
    article_update = next(u for u in coll.updates if u[0] == "one" and "payload_article_id" in u[2].get("$set", {}))
    assert article_update[2]["$set"]["payload_article_id"] == "article-123"
    # the merchant question has frequency 1 -> no draft
    assert len(created) == 1


@pytest.mark.asyncio
async def test_cluster_gap_candidates_skips_junk_even_with_demand(monkeypatch, no_alerts):
    """Regression for the first-night drafts: 'Live Agent' and a debit-card question got CMS drafts."""
    pending = [
        {"_id": "j1", "user_question": "Live Agent", "question_embedding": [1.0, 0.0], "question_frequency": 5, "generated_answer": "...", "topic_cluster": None},
        {"_id": "j2", "user_question": "Can you transfer litecoin money to my regular debit card on my checking account", "question_embedding": [0.0, 1.0], "question_frequency": 6, "generated_answer": "...", "topic_cluster": None},
        {"_id": "j3", "user_question": "Should I buy Litecoin before the halving?", "question_embedding": [0.5, 0.5], "question_frequency": 9, "generated_answer": "...", "topic_cluster": "halving"},
        {"_id": "ok", "user_question": "How does the Litecoin halving affect miners?", "question_embedding": [0.7, -0.7], "question_frequency": 4, "generated_answer": "...", "topic_cluster": "halving"},
    ]
    coll = _Coll(docs=pending)
    monkeypatch.setattr("backend.dependencies.get_knowledge_candidates_collection", AsyncMock(return_value=coll))
    created: List[Dict[str, Any]] = []

    async def _fake_draft(**kw):
        created.append(kw)
        return "a"

    monkeypatch.setattr("backend.services.article_draft_generator.create_payload_draft", _fake_draft)
    summary = await mj._cluster_gap_candidates("run5")
    assert [c["question"] for c in created] == ["How does the Litecoin halving affect miners?"]
    assert summary["skipped"] == {"too_short": 1, "no_topic_cluster": 1, "safety_refuse_financial_advice": 1}


def test_draftable_question_reasons():
    assert mj._draftable_question("Live Agent", "misc") == "too_short"
    assert mj._draftable_question("How do I bake sourdough bread at home?", "misc") == "off_topic"
    assert mj._draftable_question("What is MWEB and how do I use it?", None) == "no_topic_cluster"
    assert mj._draftable_question("What is MWEB and how do I use it?", "mweb") is None


# --------------------------------------------------------------------------- reconcile


@pytest.mark.asyncio
async def test_reconcile_embeddings_enqueues_missing_stale_and_orphans(monkeypatch, no_alerts):
    now = datetime.now(timezone.utc)
    published = [
        {"id": "p1", "updatedAt": (now - timedelta(days=2)).isoformat()},  # indexed, current
        {"id": "p2", "updatedAt": now.isoformat()},                          # indexed, but index is old -> stale
        {"id": "p3", "updatedAt": now.isoformat()},                          # missing from index
    ]
    monkeypatch.setattr(mj, "_payload_published_docs", AsyncMock(return_value=published))
    db = _DB()
    db["litecoin_docs"] = _Coll(
        agg=[
            {"_id": "p1", "updated_at": now - timedelta(days=2)},
            {"_id": "p2", "updated_at": now - timedelta(days=3)},
            {"_id": "orphan", "updated_at": now},
        ]
    )
    monkeypatch.setattr(mj, "_mongo_db", AsyncMock(return_value=db))
    ingest = AsyncMock(return_value="j")
    delete = AsyncMock(return_value="j")
    monkeypatch.setattr("backend.jobs.enqueue.enqueue_ingest", ingest)
    monkeypatch.setattr("backend.jobs.enqueue.enqueue_delete", delete)

    summary = await mj._reconcile_embeddings("run4")
    assert summary["missing"] == 1 and summary["stale"] == 1 and summary["orphans"] == 1
    assert ingest.await_count == 2
    delete.assert_awaited_once_with("orphan", "unpublish")
    assert no_alerts and no_alerts[0]["level"] == "warning"


# --------------------------------------------------------------------------- run wrapper + status


@pytest.mark.asyncio
async def test_run_wrapper_records_status_and_alerts_on_failure(monkeypatch):
    starts: List[str] = []
    finishes: List[Any] = []
    alerts: List[str] = []

    async def _start(name):
        starts.append(name)
        return "rid"

    async def _finish(name, run_id, status, summary=None, error=None):
        finishes.append((name, run_id, status, summary, error))

    async def _alert(title, description, level="info", fields=None):
        alerts.append(level)

    monkeypatch.setattr(mj, "record_job_start", _start)
    monkeypatch.setattr(mj, "record_job_finish", _finish)
    monkeypatch.setattr(mj, "_alert", _alert)

    async def ok(run_id):
        return {"n": 1}

    async def boom(run_id):
        raise RuntimeError("nope")

    assert await mj._run("j1", ok) == {"n": 1}
    with pytest.raises(RuntimeError):
        await mj._run("j2", boom)
    assert finishes[0][2] == "success" and finishes[1][2] == "error"
    assert alerts == ["error"]


def test_scheduled_jobs_registry_matches_worker_functions():
    from backend.jobs.enqueue import MAINTENANCE_JOBS
    from backend.jobs.status import SCHEDULED_JOBS

    assert set(MAINTENANCE_JOBS) == set(SCHEDULED_JOBS) == set(mj.JOB_FUNCTIONS)


# --------------------------------------------------------------------------- doc sources


def test_doc_sources_registry_loads_and_is_well_formed():
    from backend.data_ingestion.doc_sources import REGISTRY_PATH, load_registry

    specs = load_registry(REGISTRY_PATH)
    ids = [s.id for s in specs]
    assert len(ids) == len(set(ids))
    kinds = {s.kind for s in specs}
    assert kinds <= {"litecoin_com", "github_markdown", "html_page"}
    assert any(s.repo == "litecoin-project/litecoin" for s in specs)
    assert any("lip-0003" in p for s in specs for p in s.paths)  # MWEB LIP
    assert all(s.tier in ("cms", "pinned", "web") for s in specs)


def test_mediawiki_to_markdown_basics():
    from backend.data_ingestion.doc_sources import mediawiki_to_markdown

    src = "== Abstract ==\nThis is '''bold''' and ''italic''.\n* item one\n* item two\n[https://example.org Example]\n<pre>\ncode\n</pre>\n"
    md = mediawiki_to_markdown(src)
    assert "## Abstract" in md
    assert "**bold**" in md and "*italic*" in md
    assert "- item one" in md
    assert "[Example](https://example.org)" in md
    assert "```\ncode\n```" in md


@pytest.mark.asyncio
async def test_fetch_github_markdown_handles_404_and_thin(monkeypatch):
    from backend.data_ingestion import doc_sources as ds

    class _Resp:
        def __init__(self, status, text=""):
            self.status_code = status
            self.text = text

        def json(self):
            return []

    class _Client:
        async def get(self, url, **kw):
            if url.endswith("missing.md"):
                return _Resp(404)
            if url.endswith("thin.md"):
                return _Resp(200, "# Tiny\nshort")
            return _Resp(200, "# Release Notes 0.21\n" + "word " * 120)

    spec = ds.SourceSpec(id="t", kind="github_markdown", repo="x/y", paths=["doc/missing.md", "doc/thin.md", "doc/release-notes.md"], tier="pinned", review_interval_days=90, title_prefix="Litecoin Core")
    docs = await ds.fetch_github_markdown(spec, _Client())
    by_path = {d.url.rsplit("/", 1)[-1]: d for d in docs}
    assert by_path["missing.md"].skip_reason == "http_404"
    assert by_path["thin.md"].skip_reason == "thin"
    good = by_path["release-notes.md"]
    assert good.skip_reason is None
    assert good.title.startswith("Litecoin Core: Release Notes 0.21")
    assert "Imported reference (pinned)" in good.markdown
    assert good.url == "https://github.com/x/y/blob/master/doc/release-notes.md"
