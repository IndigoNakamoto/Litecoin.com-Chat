"""
Metadata-aware formatting of LangChain Documents for RAG LLM context.

Kept lightweight so tests can import without loading rag_pipeline (torch, etc.).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

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


def _iso(value: Any) -> str:
    """Best-effort ISO-8601 string for datetime-ish metadata values."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


def _is_stale(last_reviewed: Any, updated_at: Any, review_interval_days: Any) -> bool:
    """A doc is stale when its last review (or last update) is older than its review window."""
    from datetime import datetime, timedelta, timezone

    try:
        days = int(review_interval_days) if review_interval_days not in (None, "") else 0
    except (TypeError, ValueError):
        days = 0
    if days <= 0:
        return False
    anchor_raw = last_reviewed or updated_at
    if not anchor_raw:
        return False
    anchor = anchor_raw
    if not hasattr(anchor, "year"):
        try:
            anchor = datetime.fromisoformat(str(anchor_raw).replace("Z", "+00:00"))
        except ValueError:
            return False
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - anchor > timedelta(days=days)


def serialize_sources_for_client(docs: List[Document], published_only: bool = True) -> List[Dict[str, Any]]:
    """
    Structured source chips for the chat UI.

    One entry per distinct article (deduped by payload_id, then slug, then title),
    carrying title, reader URL, CMS `updated_at`, review metadata, and a `stale`
    flag. This is the trust surface: the model never writes these; retrieval does.
    """
    chips: List[Dict[str, Any]] = []
    seen: set = set()
    for doc in docs or []:
        md = doc.metadata or {}
        if published_only and md.get("status") not in (None, "published"):
            continue
        payload_id = md.get("payload_id")
        slug = md.get("slug")
        title = md.get("doc_title") or md.get("title") or "Untitled"
        key = str(payload_id or slug or title)
        if key in seen:
            continue
        seen.add(key)
        last_reviewed = md.get("last_reviewed_at")
        interval = md.get("review_interval_days")
        chips.append(
            {
                "payload_id": str(payload_id) if payload_id else None,
                "slug": str(slug) if slug else None,
                "title": str(title),
                "url": md.get("pinned_url") or _build_article_reader_url(slug) or None,
                "updated_at": _iso(md.get("updated_at")) or None,
                "last_reviewed_at": _iso(last_reviewed) or None,
                "review_interval_days": int(interval) if isinstance(interval, (int, float)) or (
                    isinstance(interval, str) and interval.isdigit()
                ) else None,
                "stale": _is_stale(last_reviewed, md.get("updated_at"), interval),
                "tier": md.get("source_tier") or "cms",
            }
        )
    return chips


def serialize_web_sources(grounding_metadata: Any) -> List[Dict[str, Any]]:
    """Web (unverified) chips from Gemini grounding metadata."""
    if not isinstance(grounding_metadata, dict):
        return []
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for chunk in grounding_metadata.get("grounding_chunks") or []:
        web = chunk.get("web") if isinstance(chunk, dict) else None
        if not isinstance(web, dict):
            continue
        uri = web.get("uri") or ""
        if not uri or uri in seen:
            continue
        seen.add(uri)
        out.append({"title": web.get("title") or uri, "url": uri, "tier": "web", "verified": False})
    return out


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
