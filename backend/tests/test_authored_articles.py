"""Editor-authored content files (content/articles) and their Payload seeding."""

import pytest

from backend.data_ingestion import authored_articles as aa


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


GOOD = """---
title: Ordinals Lite FAQ
category: Ordinals & Digital Artifacts
sourceUrl: https://example.org/faq
sourceTier: pinned
reviewIntervalDays: 90
---

# Ordinals Lite FAQ

Body paragraph about litoshis.
"""


def test_parse_article_file_reads_front_matter_and_body(tmp_path):
    a = aa.parse_article_file(_write(tmp_path, "ordinals/ordinals-lite-faq.md", GOOD))
    assert a.slug == "ordinals-lite-faq" and a.title == "Ordinals Lite FAQ"
    assert a.category == "Ordinals & Digital Artifacts" and a.source_url == "https://example.org/faq"
    assert a.tier == "pinned" and a.review_interval_days == 90
    assert a.markdown.startswith("# Ordinals Lite FAQ\n\nBody paragraph") and a.word_count > 0


def test_parse_article_file_defaults_and_adds_heading(tmp_path):
    a = aa.parse_article_file(_write(tmp_path, "x.md", "---\ntitle: Plain\n---\nJust text.\n"))
    assert a.tier == "cms" and a.review_interval_days == 180 and a.category is None and a.source_url is None
    assert a.markdown == "# Plain\n\nJust text."


@pytest.mark.parametrize(
    "text, msg",
    [
        ("# No front matter\n\nbody", "missing YAML front-matter"),
        ("---\ncategory: X\n---\nbody", "non-empty `title`"),
        ("---\ntitle: T\nsourceTier: blog\n---\nbody", "sourceTier must be one of"),
        ("---\ntitle: T\nreviewIntervalDays: soon\n---\nbody", "reviewIntervalDays must be an integer"),
        ("---\ntitle: T\n---\n\n", "empty body"),
        ("---\n- not\n- a map\n---\nbody", "must be a mapping"),
    ],
)
def test_parse_article_file_rejects_malformed(tmp_path, text, msg):
    with pytest.raises(aa.AuthoredArticleError, match=msg):
        aa.parse_article_file(_write(tmp_path, "bad.md", text))


def test_load_articles_sorts_filters_and_rejects_duplicate_titles(tmp_path):
    _write(tmp_path, "b/second.md", "---\ntitle: Second\n---\nb")
    _write(tmp_path, "a/first.md", "---\ntitle: First\n---\na")
    _write(tmp_path, "README.md", "not an article")
    assert [a.slug for a in aa.load_articles(tmp_path)] == ["first", "second"]
    assert [a.slug for a in aa.load_articles(tmp_path, only=["second"])] == ["second"]
    with pytest.raises(aa.AuthoredArticleError, match="no content file for --only"):
        aa.load_articles(tmp_path, only=["nope"])
    _write(tmp_path, "c/dupe.md", "---\ntitle: first\n---\nc")  # case-insensitive clash
    with pytest.raises(aa.AuthoredArticleError, match="duplicate title"):
        aa.load_articles(tmp_path)


def test_repo_content_directory_is_well_formed():
    """Every shipped content file parses, has a known category, and titles are unique."""
    articles = aa.load_articles(aa.CONTENT_DIR)
    assert len(articles) >= 12
    known = {
        "Ordinals & Digital Artifacts", "Build on Litecoin", "Live Network Data",
        "Fees, Payments & Everyday Use", "Mining & Network Security", "Ecosystem & Foundation",
    }
    for a in articles:
        assert a.category in known, (a.slug, a.category)
        assert a.word_count >= 150, a.slug
        # Every file carries a sources note for editors; it stays in git, never in the KB.
        assert a.editor_note and a.editor_note.startswith("---"), a.slug
        assert "Editor note" not in a.markdown, a.slug
        assert not a.markdown.rstrip().endswith("---"), a.slug
    assert sum(1 for a in articles if a.slug.startswith(("what-are-ordinals", "inscriptions", "ordinals-lite", "litescribe", "collecting"))) == 6
    space = [a for a in articles if a.path.parent.name == "litecoin-space"]
    assert len(space) == 6 and all(a.tier == "pinned" and a.source_url.startswith("https://litecoinspace.org/") for a in space)


def test_strip_editor_note_only_removes_trailing_note():
    body = "# T\n\nBody.\n\n---\n*Editor note. Sources: x. Please verify y.*\n"
    stripped, note = aa.strip_editor_note(body)
    assert stripped == "# T\n\nBody." and note.startswith("---") and "verify y" in note
    # A horizontal rule mid-article, or a note that is not last, is left alone.
    keep = "# T\n\nIntro.\n\n---\n\n## Section\n\nMore."
    assert aa.strip_editor_note(keep) == (keep, None)
    assert aa.strip_editor_note("# T\n\nno note") == ("# T\n\nno note", None)


@pytest.mark.asyncio
async def test_seed_articles_upserts_by_title_preserving_status(monkeypatch, tmp_path):
    from backend.data_ingestion import doc_sources as ds
    from backend.services import article_draft_generator as adg

    existing = {
        "pub-1": {"id": "pub-1", "title": "Published One", "status": "published", "markdown": "old"},
        "same-2": {"id": "same-2", "title": "Same Two", "status": "draft", "markdown": "# Same Two\n\nbody \\*x\\*"},
    }
    by_title = {"Published One": ["pub-1"], "Same Two": ["same-2"]}
    calls = {"create": [], "update": []}

    async def fake_find(*, source_url=None, title=None, client=None):
        return by_title.get(title, [])

    async def fake_get(article_id, client):
        return existing.get(article_id)

    async def fake_update(article_id, title, markdown, status, source_url, client, extra_fields):
        calls["update"].append((article_id, status, source_url, extra_fields))
        return article_id

    async def fake_create(title, markdown, status, source_url, client, extra_fields):
        calls["create"].append((title, status, source_url, extra_fields))
        return "new-3"

    async def fake_cat(name, client):
        return {"Build on Litecoin": "cat-build"}.get(name)

    monkeypatch.setattr(adg, "find_payload_articles", fake_find)
    monkeypatch.setattr(adg, "update_payload_article", fake_update)
    monkeypatch.setattr(adg, "create_payload_article", fake_create)
    monkeypatch.setattr(ds, "_get_article", fake_get)
    monkeypatch.setattr(ds, "resolve_category_id", fake_cat)

    _write(tmp_path, "one.md", "---\ntitle: Published One\ncategory: Build on Litecoin\nsourceUrl: https://s/1\nsourceTier: pinned\nreviewIntervalDays: 90\n---\nnew body")
    _write(tmp_path, "two.md", "---\ntitle: Same Two\n---\nbody *x*")
    _write(tmp_path, "three.md", "---\ntitle: Fresh Three\ncategory: Nope\n---\nbody")
    articles = aa.load_articles(tmp_path)

    dry = await aa.seed_articles(articles, apply=False)
    assert dry.created == [] and calls == {"create": [], "update": []}

    report = await aa.seed_articles(articles, apply=True)
    assert calls["update"] == [("pub-1", "published", "https://s/1", {"sourceTier": "pinned", "reviewIntervalDays": 90, "category": ["cat-build"]})]
    assert report.unchanged == ["same-2"]
    assert calls["create"] == [("Fresh Three", "draft", None, {"sourceTier": "cms", "reviewIntervalDays": 180})]
    assert report.created == ["new-3"] and report.updated == ["pub-1"] and report.untagged == ["three"] and report.errors == []
    text = aa.format_seed_report(articles, report, apply=True)
    assert "created=1 updated=1 unchanged=1 errors=0" in text and "three: category not found" in text
