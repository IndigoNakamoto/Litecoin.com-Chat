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
    monkeypatch.setenv("PAYLOAD_PUBLIC_SERVER_URL", "https://payload.test")
    monkeypatch.setenv("ARTICLE_PUBLIC_PATH_TEMPLATE", "/posts/{slug}")
    docs = [Document(page_content="X", metadata={"doc_title": "T", "slug": "my-post"})]
    out = format_docs(docs)
    assert "URL: https://payload.test/posts/my-post" in out


def test_format_docs_empty_slug_url_na(monkeypatch):
    monkeypatch.setenv("ARTICLE_PUBLIC_BASE_URL", "https://cms.example.com")
    docs = [Document(page_content="X", metadata={"doc_title": "T", "slug": ""})]
    out = format_docs(docs)
    assert "URL: n/a" in out


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
