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


async def create_payload_draft(
    question: str,
    answer: str,
    topic: Optional[str] = None,
    grounding_sources: Optional[List[Dict]] = None,
) -> str:
    """
    Create a draft article in Payload CMS from a knowledge gap candidate.

    Returns the Payload CMS article ID on success.
    Raises on failure.
    """
    payload_url = _get_payload_url()
    api_key = _get_payload_api_key()

    if not api_key:
        raise ValueError(
            "PAYLOAD_API_KEY environment variable is required to create CMS drafts. "
            "Set it to a Payload CMS API key with article create permissions."
        )

    markdown_content = _format_answer_as_article(question, answer, topic, grounding_sources or [])
    title = _derive_title(question, topic)

    article_data: Dict[str, Any] = {
        "title": title,
        "status": "draft",
        "markdown": markdown_content,
        "content": _build_lexical_content(markdown_content),
    }

    url = f"{payload_url}/api/articles"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"API-Key {api_key}",
    }

    logger.info("Creating Payload CMS draft article: title='%s', url=%s", title, url)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=article_data, headers=headers)

        if response.status_code in (200, 201):
            data = response.json()
            article_id = data.get("doc", {}).get("id") or data.get("id", "")
            logger.info("Payload CMS draft article created: id=%s, title='%s'", article_id, title)
            return str(article_id)
        else:
            error_text = response.text[:500]
            logger.error(
                "Failed to create Payload CMS draft: status=%d, response=%s",
                response.status_code, error_text,
            )
            raise RuntimeError(
                f"Payload CMS API returned {response.status_code}: {error_text}"
            )
