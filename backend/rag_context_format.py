"""
Metadata-aware formatting of LangChain Documents for RAG LLM context.

Kept lightweight so tests can import without loading rag_pipeline (torch, etc.).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document


def _build_article_reader_url(slug: Any, payload_id: Any = None) -> str:
    """
    Public reader URL for an article.

    Only built when ARTICLE_PUBLIC_BASE_URL is set (the chat frontend's public base,
    e.g. https://chat.lite.space/chat). The CMS host is deliberately not a fallback:
    Payload serves no public article page, so such links 404.

    Path template ARTICLE_PUBLIC_PATH_TEMPLATE may use {slug} and/or {id}; default
    "/articles/{id}" because published articles typically have no slug.
    """
    base = (os.getenv("ARTICLE_PUBLIC_BASE_URL") or "").rstrip("/")
    if not base:
        return ""
    s = str(slug).strip() if slug is not None and str(slug).strip() else ""
    pid = str(payload_id).strip() if payload_id is not None and str(payload_id).strip() else ""
    tmpl = os.getenv("ARTICLE_PUBLIC_PATH_TEMPLATE", "/articles/{id}")
    if "{slug}" in tmpl and not s:
        tmpl = "/articles/{id}"
    if "{id}" in tmpl and not pid:
        if s:
            tmpl = "/articles/{slug}"
        else:
            return ""
    try:
        path = tmpl.format(slug=s, id=pid)
    except (KeyError, ValueError, IndexError):
        path = f"/articles/{pid or s}"
    if path.startswith("http://") or path.startswith("https://"):
        return path
    path = path if path.startswith("/") else f"/{path}"
    return f"{base}{path}"


_YOUTUBE_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be", "www.youtube-nocookie.com")


def youtube_video_id(url: Any) -> str:
    """Return the 11-char YouTube video id for watch/shorts/embed/live/youtu.be URLs, else ''."""
    if not url:
        return ""
    try:
        from urllib.parse import parse_qs, urlparse

        u = urlparse(str(url).strip())
    except Exception:
        return ""
    host = (u.netloc or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return ""
    vid = ""
    if host.endswith("youtu.be"):
        vid = u.path.strip("/").split("/")[0] if u.path.strip("/") else ""
    else:
        parts = [p for p in u.path.split("/") if p]
        if u.path.startswith("/watch"):
            vid = (parse_qs(u.query).get("v") or [""])[0]
        elif parts and parts[0] in ("embed", "shorts", "live", "v") and len(parts) > 1:
            vid = parts[1]
    import re

    return vid if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid or "") else ""


def source_kind(url: Any) -> str:
    """youtube | article (our own public reader) | external (any other origin)."""
    if not url:
        return "article"
    if youtube_video_id(url):
        return "youtube"
    base = (os.getenv("ARTICLE_PUBLIC_BASE_URL") or "").rstrip("/")
    if base and str(url).startswith(base):
        return "article"
    return "external"


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


def serialize_sources_for_client(
    docs: List[Document],
    published_only: bool = True,
    max_chips: Optional[int] = None,
    known_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """
    Structured source chips for the chat UI.

    One entry per distinct article (deduped by payload_id, then slug, then title),
    carrying title, link, CMS `updated_at`, review metadata, and a `stale` flag.
    Docs arrive relevance-ordered (cross-encoder), so the first `max_chips`
    articles (SOURCE_CHIPS_MAX, default 5) are the ones worth showing.
    This is the trust surface: the model never writes these; retrieval does.
    """
    if max_chips is None:
        try:
            max_chips = int(os.getenv("SOURCE_CHIPS_MAX", "5"))
        except ValueError:
            max_chips = 5
    chips: List[Dict[str, Any]] = []
    seen: set = set()
    for doc in docs or []:
        if max_chips and len(chips) >= max_chips:
            break
        md = doc.metadata or {}
        if published_only and md.get("status") not in (None, "published"):
            continue
        payload_id = md.get("payload_id")
        slug = md.get("slug")
        title = md.get("doc_title") or md.get("title") or "Untitled"
        # Drop chips for articles that no longer exist (stale cache entries seeded
        # from another environment, deleted articles). Pinned sources have no id.
        if known_ids is not None and payload_id and str(payload_id) not in known_ids and not md.get("pinned_url"):
            continue
        key = str(payload_id or slug or title)
        if key in seen:
            continue
        seen.add(key)
        last_reviewed = md.get("last_reviewed_at")
        interval = md.get("review_interval_days")
        # Link precedence: incident-pin URL -> the article's canonical origin
        # (sourceUrl: litecoin.com page, YouTube video, ...) -> our public reader.
        reader_url = _build_article_reader_url(slug, payload_id) or None
        url = md.get("pinned_url") or md.get("source_url") or reader_url
        chips.append(
            {
                "payload_id": str(payload_id) if payload_id else None,
                "slug": str(slug) if slug else None,
                "title": str(title),
                "url": url,
                "kind": source_kind(url),
                "video_id": youtube_video_id(url) or None,
                "reader_url": reader_url,
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
        url = md.get("source_url") or _build_article_reader_url(slug_raw, md.get("payload_id"))
        url_disp = url if url else "n/a"
        body = doc.page_content or ""
        header = f"[SOURCE: {title} | URL: {url_disp}]"
        blocks.append(f"{header}\n{body}\n---")
    return "\n\n".join(blocks)
