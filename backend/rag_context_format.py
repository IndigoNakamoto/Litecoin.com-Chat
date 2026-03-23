"""
Metadata-aware formatting of LangChain Documents for RAG LLM context.

Kept lightweight so tests can import without loading rag_pipeline (torch, etc.).
"""

from __future__ import annotations

import os
from typing import Any, List

from langchain_core.documents import Document


def _build_article_reader_url(slug: Any) -> str:
    """
    Public reader URL for markdown citations [title](url).

    Configure with ARTICLE_PUBLIC_BASE_URL (falls back to PAYLOAD_PUBLIC_SERVER_URL,
    then PAYLOAD_URL). Path template: ARTICLE_PUBLIC_PATH_TEMPLATE, default "/articles/{slug}".
    """
    if slug is None or not str(slug).strip():
        return ""
    s = str(slug).strip()
    base = (
        os.getenv("ARTICLE_PUBLIC_BASE_URL")
        or os.getenv("PAYLOAD_PUBLIC_SERVER_URL")
        or os.getenv("PAYLOAD_URL")
        or ""
    ).rstrip("/")
    if not base:
        return ""
    tmpl = os.getenv("ARTICLE_PUBLIC_PATH_TEMPLATE", "/articles/{slug}")
    if "{slug}" not in tmpl:
        tmpl = "/articles/{slug}"
    try:
        path = tmpl.format(slug=s)
    except (KeyError, ValueError):
        path = f"/articles/{s}"
    if path.startswith("http://") or path.startswith("https://"):
        return path
    path = path if path.startswith("/") else f"/{path}"
    return f"{base}{path}"


def format_docs(docs: List[Document]) -> str:
    """Format documents for LLM context: SOURCE HEADER (title + reader URL), then body, then separator."""
    blocks: List[str] = []
    for doc in docs:
        md = doc.metadata or {}
        title = md.get("doc_title") or md.get("title") or "unknown"
        slug_raw = md.get("slug")
        url = _build_article_reader_url(slug_raw)
        url_disp = url if url else "n/a"
        body = doc.page_content or ""
        header = f"[SOURCE: {title} | URL: {url_disp}]"
        blocks.append(f"{header}\n{body}\n---")
    return "\n\n".join(blocks)
