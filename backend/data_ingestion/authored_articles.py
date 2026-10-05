"""
Editor-authored articles kept in the repo (`content/articles/**/*.md`) and seeded
into Payload CMS as drafts.

Each file is markdown with a YAML front-matter block:

    ---
    title: Ordinals Lite FAQ                  # required; the upsert key
    category: Ordinals & Digital Artifacts    # Payload category *name* (optional)
    sourceUrl: https://litecoinspace.org/docs/faq   # optional; source chips link here
    sourceTier: cms                           # cms | pinned | web (default cms)
    reviewIntervalDays: 180                   # default 180
    ---
    # Body in markdown ...

Semantics match `doc_sources.upsert_drafts`: new articles are created as drafts,
existing ones (matched by exact title) keep whatever status an editor set, and an
article whose title/body are unchanged is left alone. Publishing stays a human
action in the CMS.

A trailing editor note — a final `---` rule followed by an italic paragraph that
starts with "Editor note" — is kept in the repo file (sources, facts to verify)
but stripped before the body is sent to the CMS, so it is never embedded.

    python scripts/seed_articles.py --dry-run
    python scripts/seed_articles.py --apply --only ordinals-lite-faq
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx
import yaml

logger = logging.getLogger(__name__)

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "articles"
VALID_TIERS = ("cms", "pinned", "web")
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# "---" then an italic paragraph beginning "Editor note", at the very end of the file.
_EDITOR_NOTE_RE = re.compile(r"\n+---\s*\n\s*\*Editor note\b.*\*\s*\Z", re.DOTALL | re.IGNORECASE)


def strip_editor_note(body: str) -> tuple:
    """(body without the trailing editor note, the note text or None)."""
    m = _EDITOR_NOTE_RE.search(body)
    if not m:
        return body.rstrip(), None
    return body[: m.start()].rstrip(), m.group(0).strip()


class AuthoredArticleError(ValueError):
    """A content file is malformed (missing front-matter, title, bad tier...)."""


@dataclass
class AuthoredArticle:
    slug: str            # file stem, used by --only
    path: Path
    title: str
    markdown: str        # body as sent to the CMS (editor note removed)
    category: Optional[str] = None
    editor_note: Optional[str] = None
    source_url: Optional[str] = None
    tier: str = "cms"
    review_interval_days: int = 180

    @property
    def word_count(self) -> int:
        return len(re.findall(r"\b[\w']+\b", self.markdown))


@dataclass
class SeedReport:
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    untagged: List[str] = field(default_factory=list)   # category name not found in Payload


def parse_article_file(path: Path) -> AuthoredArticle:
    text = path.read_text(encoding="utf-8")
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        raise AuthoredArticleError(f"{path}: missing YAML front-matter block")
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise AuthoredArticleError(f"{path}: invalid front-matter: {e}") from e
    if not isinstance(meta, dict):
        raise AuthoredArticleError(f"{path}: front-matter must be a mapping")
    title = str(meta.get("title") or "").strip()
    if not title:
        raise AuthoredArticleError(f"{path}: front-matter needs a non-empty `title`")
    tier = str(meta.get("sourceTier") or "cms").strip()
    if tier not in VALID_TIERS:
        raise AuthoredArticleError(f"{path}: sourceTier must be one of {VALID_TIERS}, got {tier!r}")
    try:
        review = int(meta.get("reviewIntervalDays", 180))
    except (TypeError, ValueError) as e:
        raise AuthoredArticleError(f"{path}: reviewIntervalDays must be an integer") from e
    body, editor_note = strip_editor_note(text[m.end():].strip())
    if not body:
        raise AuthoredArticleError(f"{path}: empty body")
    heading = f"# {title}"
    if not body.startswith("# "):
        body = f"{heading}\n\n{body}"
    source_url = meta.get("sourceUrl")
    category = meta.get("category")
    return AuthoredArticle(
        slug=path.stem,
        path=path,
        title=title,
        markdown=body,
        category=str(category).strip() if category else None,
        editor_note=editor_note,
        source_url=str(source_url).strip() if source_url else None,
        tier=tier,
        review_interval_days=review,
    )


def load_articles(content_dir: Path = CONTENT_DIR, only: Optional[Sequence[str]] = None) -> List[AuthoredArticle]:
    """All `*.md` files under `content_dir` (recursively), sorted by path; duplicate titles are an error."""
    wanted = {s.strip() for s in (only or []) if s and s.strip()}
    articles: List[AuthoredArticle] = []
    for path in sorted(content_dir.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        if wanted and path.stem not in wanted:
            continue
        articles.append(parse_article_file(path))
    seen: Dict[str, Path] = {}
    for a in articles:
        key = a.title.strip().lower()
        if key in seen:
            raise AuthoredArticleError(f"duplicate title {a.title!r} in {seen[key]} and {a.path}")
        seen[key] = a.path
    if wanted:
        missing = wanted - {a.slug for a in articles}
        if missing:
            raise AuthoredArticleError(f"no content file for --only {sorted(missing)}")
    return articles


async def seed_articles(articles: Sequence[AuthoredArticle], apply: bool) -> SeedReport:
    """Create/update Payload drafts for authored articles. Dry-run only reports."""
    from backend.data_ingestion.doc_sources import _get_article, markdown_fingerprint, resolve_category_id
    from backend.services.article_draft_generator import (
        create_payload_article,
        find_payload_articles,
        update_payload_article,
    )

    report = SeedReport()
    if not apply:
        return report

    category_cache: Dict[str, Optional[str]] = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for a in articles:
            extra: Dict[str, Any] = {"sourceTier": a.tier, "reviewIntervalDays": a.review_interval_days}
            if a.category:
                if a.category not in category_cache:
                    category_cache[a.category] = await resolve_category_id(a.category, client)
                cat_id = category_cache[a.category]
                if cat_id:
                    extra["category"] = [cat_id]
                else:
                    report.untagged.append(a.slug)
                    logger.warning("[%s] category %r not found in Payload; draft will be untagged", a.slug, a.category)
            try:
                existing = await find_payload_articles(title=a.title, client=client)
                if existing:
                    current = await _get_article(existing[0], client) or {}
                    cur_title = current.get("title")
                    cur_title = cur_title.get("en") if isinstance(cur_title, dict) else cur_title
                    if (
                        markdown_fingerprint(current.get("markdown") or "") == markdown_fingerprint(a.markdown)
                        and (cur_title or "").strip() == a.title.strip()
                    ):
                        report.unchanged.append(existing[0])
                        continue
                    status = current.get("status") if current.get("status") in ("draft", "published") else "draft"
                    aid = await update_payload_article(
                        existing[0], title=a.title, markdown=a.markdown, status=status,
                        source_url=a.source_url, client=client, extra_fields=extra,
                    )
                    report.updated.append(aid)
                else:
                    aid = await create_payload_article(
                        title=a.title, markdown=a.markdown, status="draft",
                        source_url=a.source_url, client=client, extra_fields=extra,
                    )
                    report.created.append(aid)
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] upsert failed: %s", a.slug, e)
                report.errors.append(f"{a.slug}: {e}")
    return report


def format_seed_report(articles: Sequence[AuthoredArticle], report: SeedReport, apply: bool) -> str:
    lines = [f"{len(articles)} authored article(s) in {CONTENT_DIR}"]
    for a in articles:
        rel = a.path.relative_to(CONTENT_DIR) if CONTENT_DIR in a.path.parents else a.path
        lines.append(
            f"  - {a.title}  [{rel}; {a.word_count} words; {a.tier}; "
            f"{a.category or 'no category'}; {a.source_url or 'reader link'}]"
        )
    if apply:
        lines.append(
            f"created={len(report.created)} updated={len(report.updated)} "
            f"unchanged={len(report.unchanged)} errors={len(report.errors)}"
        )
        for slug in report.untagged:
            lines.append(f"  ~ {slug}: category not found in Payload (create it, then re-run)")
        for e in report.errors:
            lines.append(f"  ! {e}")
    else:
        lines.append("[dry-run] no CMS writes; use --apply to create/update drafts")
    return "\n".join(lines)
