"""Tests for metadata-aware context formatting (format_docs)."""

import pytest
from langchain_core.documents import Document

from backend.rag_context_format import format_docs


def test_format_docs_empty():
    assert format_docs([]) == ""


def test_format_docs_minimal_metadata(monkeypatch):
    monkeypatch.delenv("ARTICLE_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("PAYLOAD_PUBLIC_SERVER_URL", raising=False)
    monkeypatch.delenv("PAYLOAD_URL", raising=False)
    docs = [Document(page_content="Body text.", metadata={})]
    out = format_docs(docs)
    assert "[SOURCE: unknown | URL: n/a]" in out
    assert "Body text." in out
    assert out.endswith("---")
    assert "None" not in out


def test_format_docs_builds_reader_url(monkeypatch):
    monkeypatch.setenv("ARTICLE_PUBLIC_BASE_URL", "https://cms.example.com")
    docs = [
        Document(
            page_content="First chunk.",
            metadata={"doc_title": "Halving Guide", "slug": "halving-guide"},
        )
    ]
    out = format_docs(docs)
    assert "[SOURCE: Halving Guide | URL: https://cms.example.com/articles/halving-guide]" in out
    assert "First chunk." in out
    assert "None" not in out
    assert "PUBLISHED" not in out


def test_format_docs_custom_path_template(monkeypatch):
    monkeypatch.setenv("ARTICLE_PUBLIC_BASE_URL", "https://chat.test/chat")
    monkeypatch.setenv("ARTICLE_PUBLIC_PATH_TEMPLATE", "/posts/{slug}")
    docs = [Document(page_content="X", metadata={"doc_title": "T", "slug": "my-post"})]
    out = format_docs(docs)
    assert "URL: https://chat.test/chat/posts/my-post" in out


def test_format_docs_cms_host_is_not_a_fallback(monkeypatch):
    """Payload has no public article page; never link readers to the CMS host."""
    monkeypatch.delenv("ARTICLE_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("PAYLOAD_PUBLIC_SERVER_URL", "https://cms.test")
    monkeypatch.delenv("ARTICLE_PUBLIC_PATH_TEMPLATE", raising=False)
    docs = [Document(page_content="X", metadata={"doc_title": "T", "slug": "s", "payload_id": "p1"})]
    assert "URL: n/a" in format_docs(docs)


def test_format_docs_reader_url_by_payload_id_when_no_slug(monkeypatch):
    monkeypatch.setenv("ARTICLE_PUBLIC_BASE_URL", "https://chat.test/chat")
    monkeypatch.delenv("ARTICLE_PUBLIC_PATH_TEMPLATE", raising=False)
    docs = [Document(page_content="X", metadata={"doc_title": "T", "payload_id": "66aa"})]
    assert "URL: https://chat.test/chat/articles/66aa" in format_docs(docs)


def test_format_docs_prefers_source_url(monkeypatch):
    monkeypatch.setenv("ARTICLE_PUBLIC_BASE_URL", "https://chat.test/chat")
    docs = [Document(page_content="X", metadata={"doc_title": "T", "payload_id": "p", "source_url": "https://litecoin.com/learning-center/x"})]
    assert "URL: https://litecoin.com/learning-center/x" in format_docs(docs)


def test_format_docs_empty_slug_url_na(monkeypatch):
    monkeypatch.setenv("ARTICLE_PUBLIC_BASE_URL", "https://cms.example.com")
    monkeypatch.delenv("ARTICLE_PUBLIC_PATH_TEMPLATE", raising=False)
    docs = [Document(page_content="X", metadata={"doc_title": "T", "slug": ""})]
    out = format_docs(docs)
    assert "URL: n/a" in out


def test_youtube_video_id_and_kind(monkeypatch):
    from backend.rag_context_format import source_kind, youtube_video_id

    monkeypatch.setenv("ARTICLE_PUBLIC_BASE_URL", "https://chat.test/chat")
    assert youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://www.youtube.com/@litecoin") == ""
    assert youtube_video_id("https://litecoin.com/learning-center/mweb") == ""
    assert source_kind("https://youtu.be/dQw4w9WgXcQ") == "youtube"
    assert source_kind("https://chat.test/chat/articles/abc") == "article"
    assert source_kind("https://litecoin.com/learning-center/mweb") == "external"
    assert source_kind(None) == "article"


def test_format_docs_multiple_chunks(monkeypatch):
    monkeypatch.setenv("ARTICLE_PUBLIC_BASE_URL", "https://cms.example.com")
    docs = [
        Document(page_content="A", metadata={"doc_title": "One", "slug": "one"}),
        Document(page_content="B", metadata={"doc_title": "Two", "slug": "two"}),
    ]
    out = format_docs(docs)
    assert out.count("---") == 2
    assert "[SOURCE: One |" in out
    assert "[SOURCE: Two |" in out
    assert "/articles/one" in out
    assert "/articles/two" in out
