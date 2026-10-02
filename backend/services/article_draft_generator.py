"""
Article Draft Generator

Takes an approved knowledge gap candidate and creates a draft article
in Payload CMS via its REST API. The admin can then review, edit, and
publish the article, which triggers the existing webhook pipeline to
chunk, embed, and add it to the vector store.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from backend.services.llm_resilience import call_with_payload_breaker

logger = logging.getLogger(__name__)


def _get_payload_url() -> str:
    return (
        os.getenv("PAYLOAD_URL")
        or os.getenv("PAYLOAD_PUBLIC_SERVER_URL")
        or "https://cms.lite.space"
    )


def _get_payload_api_key() -> Optional[str]:
    return os.getenv("PAYLOAD_API_KEY")


def _format_answer_as_article(question: str, answer: str, topic: Optional[str], grounding_sources: List[Dict]) -> str:
    """
    Format the generated answer into a structured article markdown
    following the article template guide conventions.
    """
    title = _derive_title(question, topic)

    sections = [f"# {title}\n"]

    # If the answer already has markdown headings, use it mostly as-is
    has_headings = bool(re.search(r"^#{1,3}\s", answer, re.MULTILINE))
    if has_headings:
        sections.append(answer.strip())
    else:
        sections.append(f"## Overview\n\n{answer.strip()}")

    # Append sourcing provenance if grounding sources exist
    if grounding_sources:
        sections.append("\n## Sources\n")
        for src in grounding_sources:
            url = src.get("url", "")
            src_title = src.get("title", url)
            if url:
                sections.append(f"- [{src_title}]({url})")
            elif src_title:
                sections.append(f"- {src_title}")

    sections.append(
        "\n---\n*This article was auto-generated from a knowledge gap detection. "
        "Please review and edit before publishing.*"
    )

    return "\n\n".join(sections)


def _derive_title(question: str, topic: Optional[str]) -> str:
    """Derive an article title from the user question."""
    q = question.strip().rstrip("?").strip()
    q = re.sub(r"^(what is|what are|how does|how do|explain|tell me about|describe)\s+", "", q, flags=re.IGNORECASE)
    if not q:
        q = topic or "Litecoin Topic"
    # Title-case the result
    return q[0].upper() + q[1:] if q else "Litecoin Topic"


def _build_lexical_content(markdown_text: str) -> Dict[str, Any]:
    """
    Build a minimal Lexical JSON structure for Payload CMS.
    Payload CMS uses Lexical for rich text; we wrap the markdown in a
    single paragraph node as a starting point for admin editing.
    """
    return {
        "root": {
            "type": "root",
            "children": [
                {
                    "type": "paragraph",
                    "children": [
                        {
                            "type": "text",
                            "text": markdown_text,
                        }
                    ],
                    "direction": "ltr",
                    "format": "",
                    "indent": 0,
                    "version": 1,
                }
            ],
            "direction": "ltr",
            "format": "",
            "indent": 0,
            "version": 1,
        }
    }


def _payload_headers() -> Dict[str, str]:
    api_key = _get_payload_api_key()
    if not api_key:
        raise ValueError(
            "PAYLOAD_API_KEY environment variable is required to create CMS articles. "
            "Set it to a Payload CMS API key with article create permissions."
        )
    return {
        "Content-Type": "application/json",
        # Official Payload user-API-key header (works when a CMS user has enableAPIKey).
        "Authorization": f"users API-Key {api_key}",
        # Shared-secret fallback: CMS compares this to its own PAYLOAD_API_KEY.
        # Needed because a random env UUID is not a Payload user API key.
        "X-Payload-Service-Key": api_key,
    }


def _article_id_from_response(data: Dict[str, Any]) -> str:
    docs = data.get("docs") or [{}]
    first_doc = docs[0] if docs else {}
    return str(data.get("doc", {}).get("id") or data.get("id") or first_doc.get("id") or "")


def _raise_payload_error(status_code: int, error_text: str) -> None:
    logger.error(
        "Failed Payload CMS article request: status=%d, response=%s",
        status_code, error_text,
    )
    if status_code == 403:
        raise RuntimeError(
            "Payload CMS denied article create (403). PAYLOAD_API_KEY must match "
            "the CMS PAYLOAD_API_KEY env var, or be an enabled user API key on an "
            f"admin/publisher account. Response: {error_text}"
        )
    raise RuntimeError(f"Payload CMS API returned {status_code}: {error_text}")


async def create_payload_article(
    title: str,
    markdown: str,
    status: str = "draft",
    source_url: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create an article in Payload CMS.

    Args:
        status: "draft" or "published". Published articles trigger the webhook
            pipeline to sync into the vector store.
        source_url: Optional canonical URL for imported pages (idempotent re-runs).
        extra_fields: Additional Article fields (e.g. sourceTier, reviewIntervalDays).

    Returns the Payload CMS article ID on success.
    """
    if status not in ("draft", "published"):
        raise ValueError(f"Invalid status: {status!r}. Must be 'draft' or 'published'.")

    payload_url = _get_payload_url()
    headers = _payload_headers()
    article_data = _article_payload(title, markdown, status, source_url, extra_fields)

    url = f"{payload_url}/api/articles"
    logger.info("Creating Payload CMS %s article: title='%s', url=%s", status, title, url)

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0)
    try:
        response = await call_with_payload_breaker(
            lambda: http.post(url, json=article_data, headers=headers)
        )
        if (
            source_url
            and response.status_code == 400
            and "sourceUrl" in response.text
        ):
            article_data.pop("sourceUrl", None)
            logger.warning("CMS rejected sourceUrl; retrying create without it")
            response = await http.post(url, json=article_data, headers=headers)
        if response.status_code in (200, 201):
            article_id = _article_id_from_response(response.json())
            logger.info("Payload CMS %s article created: id=%s, title='%s'", status, article_id, title)
            return article_id
        _raise_payload_error(response.status_code, response.text[:500])
    finally:
        if owns_client:
            await http.aclose()
    raise RuntimeError("Payload CMS article create returned no id")


def _localized_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("en") or next(iter(value.values()), "") or "")
    return str(value or "")


async def find_payload_articles(
    *,
    source_url: Optional[str] = None,
    title: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> List[str]:
    """Return existing article ids matching sourceUrl or title."""
    if not source_url and not title:
        return []

    payload_url = _get_payload_url()
    headers = _payload_headers()
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0)
    found: List[str] = []
    seen: set[str] = set()
    try:
        lookups: List[tuple[str, str]] = []
        if source_url:
            lookups.append(("sourceUrl", source_url))
        if title and title.strip().lower() not in {"litecoin", "untitled"}:
            lookups.append(("title", title))

        for field_name, expected in lookups:
            params = {
                f"where[{field_name}][equals]": expected,
                "limit": 20,
                "locale": "en",
            }
            response = await call_with_payload_breaker(
                lambda: http.get(f"{payload_url}/api/articles", params=params, headers=headers)
            )
            if response.status_code == 400 and field_name == "sourceUrl":
                logger.warning("Payload sourceUrl query rejected; falling back to title match")
                continue
            if response.status_code not in (200, 201):
                logger.warning(
                    "Payload article lookup failed: status=%d, body=%s",
                    response.status_code,
                    response.text[:300],
                )
                continue
            for doc in response.json().get("docs") or []:
                actual = _localized_text(doc.get(field_name) if field_name == "sourceUrl" else doc.get("title"))
                if actual.strip() != expected.strip():
                    continue
                article_id = str(doc.get("id") or "")
                if article_id and article_id not in seen:
                    seen.add(article_id)
                    found.append(article_id)
        return found
    finally:
        if owns_client:
            await http.aclose()


async def find_payload_article(
    *,
    source_url: Optional[str] = None,
    title: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[str]:
    """Return an existing article id matching sourceUrl or title, if any."""
    ids = await find_payload_articles(source_url=source_url, title=title, client=client)
    return ids[0] if ids else None


def _article_payload(
    title: str,
    markdown: str,
    status: str,
    source_url: Optional[str],
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "title": title,
        "status": status,
        "markdown": markdown,
        "content": _build_lexical_content(markdown),
    }
    if source_url:
        data["sourceUrl"] = source_url
    for key, value in (extra_fields or {}).items():
        if value is not None:
            data[key] = value
    return data


async def update_payload_article(
    article_id: str,
    title: str,
    markdown: str,
    status: str = "draft",
    source_url: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> str:
    """Replace an existing Payload article's title and body."""
    if status not in ("draft", "published"):
        raise ValueError(f"Invalid status: {status!r}. Must be 'draft' or 'published'.")

    payload_url = _get_payload_url()
    headers = _payload_headers()
    article_data = _article_payload(title, markdown, status, source_url, extra_fields)
    url = f"{payload_url}/api/articles/{article_id}"
    logger.info("Updating Payload CMS %s article: id=%s title='%s'", status, article_id, title)

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0)
    try:
        response = await call_with_payload_breaker(
            lambda: http.patch(url, json=article_data, headers=headers)
        )
        if (
            source_url
            and response.status_code == 400
            and "sourceUrl" in response.text
        ):
            article_data.pop("sourceUrl", None)
            logger.warning("CMS rejected sourceUrl; retrying update without it")
            response = await http.patch(url, json=article_data, headers=headers)
        if response.status_code in (200, 201):
            logger.info("Payload CMS article updated: id=%s, title='%s'", article_id, title)
            return article_id
        _raise_payload_error(response.status_code, response.text[:500])
    finally:
        if owns_client:
            await http.aclose()
    raise RuntimeError("Payload CMS article update failed")


async def delete_payload_article(
    article_id: str,
    client: Optional[httpx.AsyncClient] = None,
) -> None:
    payload_url = _get_payload_url()
    headers = _payload_headers()
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0)
    try:
        response = await call_with_payload_breaker(
            lambda: http.delete(f"{payload_url}/api/articles/{article_id}", headers=headers)
        )
        if response.status_code not in (200, 204):
            _raise_payload_error(response.status_code, response.text[:500])
        logger.info("Payload CMS article deleted: id=%s", article_id)
    finally:
        if owns_client:
            await http.aclose()


async def create_payload_draft(
    question: str,
    answer: str,
    topic: Optional[str] = None,
    grounding_sources: Optional[List[Dict]] = None,
    publish_status: str = "draft",
) -> str:
    """
    Create an article in Payload CMS from a knowledge gap candidate.

    Args:
        publish_status: "draft" or "published". When "published", the article
            goes live immediately and triggers the webhook pipeline to sync
            into the vector store.

    Returns the Payload CMS article ID on success.
    Raises on failure.
    """
    markdown_content = _format_answer_as_article(question, answer, topic, grounding_sources or [])
    title = _derive_title(question, topic)
    return await create_payload_article(
        title=title,
        markdown=markdown_content,
        status=publish_status,
    )
