"""
Scheduled reference-doc ingestion driven by `doc_sources.yaml`.

Generalizes the litecoin.com scraper into a registry: Litecoin Core docs and
release notes, the MWEB LIPs, the Litecoin Space API reference, and the
Learning Center. Each source becomes Payload CMS drafts upserted by
`sourceUrl`, tagged with `sourceTier` and `reviewIntervalDays`. Publishing
stays a human action.

Run on a weekly ARQ cron (`ingest_doc_sources`) or by hand:

    python scripts/ingest_doc_sources.py --dry-run
    python scripts/ingest_doc_sources.py --apply --only litecoin_core_release_notes
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx
import yaml

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).with_name("doc_sources.yaml")
RAW_BASE = "https://raw.githubusercontent.com"
API_BASE = "https://api.github.com"
USER_AGENT = "LitecoinKnowledgeHub-DocIngest/1.0 (+https://litecoin.com/chat)"
DEFAULT_MIN_WORDS = 50
REQUEST_DELAY_SECONDS = float(os.getenv("DOC_SOURCES_REQUEST_DELAY", "0.5"))


@dataclass
class SourceSpec:
    id: str
    kind: str
    enabled: bool = True
    tier: str = "pinned"
    review_interval_days: int = 180
    repo: Optional[str] = None
    ref: str = "master"
    paths: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    include_glob: Optional[str] = None
    max_files: Optional[int] = None
    title_prefix: Optional[str] = None
    min_words: int = DEFAULT_MIN_WORDS

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SourceSpec":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class FetchedDoc:
    source_id: str
    url: str
    title: str
    markdown: str
    word_count: int
    tier: str
    review_interval_days: int
    skip_reason: Optional[str] = None


@dataclass
class SourceReport:
    source_id: str
    fetched: List[FetchedDoc] = field(default_factory=list)
    skipped: List[FetchedDoc] = field(default_factory=list)
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "fetched": len(self.fetched),
            "skipped": len(self.skipped),
            "created": len(self.created),
            "updated": len(self.updated),
            "errors": self.errors[:10],
        }


def load_registry(path: Path = REGISTRY_PATH) -> List[SourceSpec]:
    data = yaml.safe_load(path.read_text()) or {}
    return [SourceSpec.from_dict(s) for s in data.get("sources") or []]


# --------------------------------------------------------------------------- text helpers


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def mediawiki_to_markdown(text: str) -> str:
    """Light MediaWiki -> Markdown for the LIP files. Good enough for retrieval."""
    out: List[str] = []
    in_pre = False
    for line in text.splitlines():
        if line.startswith("<pre>") or line.startswith("<source") or line.startswith("<syntaxhighlight"):
            in_pre = True
            out.append("```")
            line = re.sub(r"<(pre|source|syntaxhighlight)[^>]*>", "", line)
            if line.strip():
                out.append(line)
            continue
        if "</pre>" in line or "</source>" in line or "</syntaxhighlight>" in line:
            line = re.sub(r"</(pre|source|syntaxhighlight)>", "", line)
            if line.strip():
                out.append(line)
            out.append("```")
            in_pre = False
            continue
        if in_pre:
            out.append(line)
            continue
        m = re.match(r"^(={2,6})\s*(.*?)\s*\1\s*$", line)
        if m:
            out.append("#" * len(m.group(1)) + " " + m.group(2))
            continue
        line = re.sub(r"'''(.+?)'''", r"**\1**", line)
        line = re.sub(r"''(.+?)''", r"*\1*", line)
        line = re.sub(r"\[(https?://\S+)\s+([^\]]+)\]", r"[\2](\1)", line)
        line = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", line)
        line = re.sub(r"\[\[([^\]]+)\]\]", r"\1", line)
        line = re.sub(r"<code>(.+?)</code>", r"`\1`", line)
        line = re.sub(r"</?nowiki>", "", line)
        if re.match(r"^\*+\s", line):
            depth = len(line) - len(line.lstrip("*"))
            line = "  " * (depth - 1) + "- " + line.lstrip("*").strip()
        elif re.match(r"^#+\s", line) and not line.startswith("# "):
            depth = len(line) - len(line.lstrip("#"))
            line = "  " * (depth - 1) + "1. " + line.lstrip("#").strip()
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _title_from_markdown(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def _title_from_filename(path: str) -> str:
    name = Path(path).stem
    name = re.sub(r"[-_]+", " ", name).strip()
    return name[:1].upper() + name[1:] if name else path


def format_import_markdown(title: str, body: str, source_url: str, tier: str) -> str:
    body = body.strip()
    heading = f"# {title}"
    parts = [body] if body.startswith(heading) else [heading, "", body]
    parts += [
        "",
        "---",
        f"*Imported reference ({tier}) from [{source_url}]({source_url}). "
        "Review before publishing; re-imports overwrite this draft.*",
    ]
    return "\n".join(parts)


def html_to_markdown(html: str, url: str) -> tuple:
    """Main-content extraction for a single HTML page. Returns (title, markdown)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(" ", strip=True)
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines: List[str] = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "code", "td", "th"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            lines.append("#" * int(el.name[1]) + " " + text)
        elif el.name == "li":
            lines.append("- " + text)
        elif el.name == "pre":
            lines.append("```\n" + el.get_text("\n", strip=False).strip() + "\n```")
        elif el.name == "code" and el.parent and el.parent.name == "pre":
            continue
        else:
            lines.append(text)
    md = re.sub(r"\n{3,}", "\n\n", "\n\n".join(lines)).strip()
    return (title or url, md)


# --------------------------------------------------------------------------- fetchers


class _Client:
    def __init__(self, client: httpx.AsyncClient, delay: float = REQUEST_DELAY_SECONDS):
        self._c = client
        self._delay = delay
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def get(self, url: str, **kw) -> httpx.Response:
        async with self._lock:
            loop = asyncio.get_event_loop()
            wait = self._delay - (loop.time() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            resp = await self._c.get(url, **kw)
            self._last = loop.time()
            return resp


def _github_headers() -> Dict[str, str]:
    h = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def _list_github_dir(client: _Client, repo: str, ref: str, path: str) -> List[str]:
    url = f"{API_BASE}/repos/{repo}/contents/{path.strip('/')}?ref={ref}"
    resp = await client.get(url, headers=_github_headers())
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub list {repo}/{path}@{ref} -> {resp.status_code}")
    items = resp.json()
    if isinstance(items, dict):  # it was a file, not a dir
        return [items.get("path") or path]
    return [i["path"] for i in items if i.get("type") == "file"]


async def fetch_github_markdown(spec: SourceSpec, client: _Client) -> List[FetchedDoc]:
    docs: List[FetchedDoc] = []
    files: List[str] = []
    for p in spec.paths:
        is_dir = not Path(p).suffix
        if is_dir:
            try:
                listed = await _list_github_dir(client, spec.repo or "", spec.ref, p)
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] %s", spec.id, e)
                docs.append(FetchedDoc(spec.id, f"https://github.com/{spec.repo}/tree/{spec.ref}/{p}", p, "", 0, spec.tier, spec.review_interval_days, skip_reason="list_error"))
                continue
            if spec.include_glob:
                listed = [f for f in listed if fnmatch.fnmatch(Path(f).name, spec.include_glob)]
            listed = sorted(listed, reverse=True)
            if spec.max_files:
                listed = listed[: spec.max_files]
            files.extend(listed)
        else:
            files.append(p)

    for path in files:
        url = f"https://github.com/{spec.repo}/blob/{spec.ref}/{path}"
        raw_url = f"{RAW_BASE}/{spec.repo}/{spec.ref}/{path}"
        try:
            resp = await client.get(raw_url, headers={"User-Agent": USER_AGENT})
        except Exception as e:  # noqa: BLE001
            docs.append(FetchedDoc(spec.id, url, path, "", 0, spec.tier, spec.review_interval_days, skip_reason=f"fetch_error: {e}"))
            continue
        if resp.status_code != 200:
            docs.append(FetchedDoc(spec.id, url, path, "", 0, spec.tier, spec.review_interval_days, skip_reason=f"http_{resp.status_code}"))
            continue
        text = resp.text
        body = mediawiki_to_markdown(text) if path.endswith(".mediawiki") else text.strip()
        fallback = _title_from_filename(path)
        title = _title_from_markdown(body, fallback)
        if spec.title_prefix and not title.lower().startswith(spec.title_prefix.lower()):
            title = f"{spec.title_prefix}: {title}"
        wc = _word_count(body)
        if wc < spec.min_words:
            docs.append(FetchedDoc(spec.id, url, title, body, wc, spec.tier, spec.review_interval_days, skip_reason="thin"))
            continue
        docs.append(FetchedDoc(spec.id, url, title, format_import_markdown(title, body, url, spec.tier), wc, spec.tier, spec.review_interval_days))
    return docs


async def fetch_html_pages(spec: SourceSpec, client: _Client) -> List[FetchedDoc]:
    docs: List[FetchedDoc] = []
    for url in spec.urls:
        try:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, follow_redirects=True)
        except Exception as e:  # noqa: BLE001
            docs.append(FetchedDoc(spec.id, url, url, "", 0, spec.tier, spec.review_interval_days, skip_reason=f"fetch_error: {e}"))
            continue
        if resp.status_code != 200:
            docs.append(FetchedDoc(spec.id, url, url, "", 0, spec.tier, spec.review_interval_days, skip_reason=f"http_{resp.status_code}"))
            continue
        title, body = html_to_markdown(resp.text, url)
        if spec.title_prefix and not title.lower().startswith(spec.title_prefix.lower()):
            title = f"{spec.title_prefix}: {title}"
        wc = _word_count(body)
        if wc < spec.min_words:
            # JS-rendered pages (e.g. mempool-based explorers) come back nearly empty; report, do not guess.
            docs.append(FetchedDoc(spec.id, url, title, body, wc, spec.tier, spec.review_interval_days, skip_reason="thin_or_js_rendered"))
            continue
        docs.append(FetchedDoc(spec.id, url, title, format_import_markdown(title, body, url, spec.tier), wc, spec.tier, spec.review_interval_days))
    return docs


async def fetch_litecoin_com(spec: SourceSpec, apply: bool) -> SourceReport:
    """Delegate to the existing Learning Center scraper (it already upserts drafts)."""
    from backend.data_ingestion.litecoin_com_scraper import run_ingest

    report = SourceReport(source_id=spec.id)
    try:
        r = await run_ingest(apply=apply, min_words=spec.min_words)
    except Exception as e:  # noqa: BLE001
        report.errors.append(str(e))
        return report
    for page in r.extracted:
        report.fetched.append(FetchedDoc(spec.id, page.url, page.title, page.markdown, page.word_count, spec.tier, spec.review_interval_days))
    for page in r.skipped:
        report.skipped.append(FetchedDoc(spec.id, page.url, page.title, "", page.word_count, spec.tier, spec.review_interval_days, skip_reason=page.skip_reason))
    for _page, article_id, action in r.written:
        (report.created if action == "created" else report.updated).append(article_id)
    return report


# --------------------------------------------------------------------------- upsert


async def upsert_drafts(docs: Sequence[FetchedDoc], report: SourceReport) -> None:
    from backend.services.article_draft_generator import (
        create_payload_article,
        find_payload_articles,
        update_payload_article,
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        for d in docs:
            if d.skip_reason:
                continue
            extra = {"sourceTier": d.tier, "reviewIntervalDays": d.review_interval_days}
            try:
                existing = await find_payload_articles(source_url=d.url, client=client)
                if existing:
                    aid = await update_payload_article(existing[0], title=d.title, markdown=d.markdown, status="draft", source_url=d.url, client=client, extra_fields=extra)
                    report.updated.append(aid)
                else:
                    aid = await create_payload_article(title=d.title, markdown=d.markdown, status="draft", source_url=d.url, client=client, extra_fields=extra)
                    report.created.append(aid)
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] upsert failed for %s: %s", d.source_id, d.url, e)
                report.errors.append(f"{d.url}: {e}")


# --------------------------------------------------------------------------- orchestration


async def run_source(spec: SourceSpec, apply: bool, client: _Client) -> SourceReport:
    if spec.kind == "litecoin_com":
        return await fetch_litecoin_com(spec, apply)

    report = SourceReport(source_id=spec.id)
    if spec.kind == "github_markdown":
        docs = await fetch_github_markdown(spec, client)
    elif spec.kind == "html_page":
        docs = await fetch_html_pages(spec, client)
    else:
        report.errors.append(f"unknown kind {spec.kind!r}")
        return report
    for d in docs:
        (report.skipped if d.skip_reason else report.fetched).append(d)
    if apply:
        await upsert_drafts(report.fetched, report)
    return report


async def run_all(apply: bool = False, only: Optional[Sequence[str]] = None, registry_path: Path = REGISTRY_PATH) -> List[SourceReport]:
    specs = [s for s in load_registry(registry_path) if s.enabled and (not only or s.id in only)]
    reports: List[SourceReport] = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as raw:
        client = _Client(raw)
        for spec in specs:
            logger.info("[doc-sources] %s (%s) apply=%s", spec.id, spec.kind, apply)
            try:
                reports.append(await run_source(spec, apply, client))
            except Exception as e:  # noqa: BLE001
                logger.error("[doc-sources] %s failed: %s", spec.id, e, exc_info=True)
                r = SourceReport(source_id=spec.id)
                r.errors.append(str(e))
                reports.append(r)
    return reports


def format_reports(reports: Sequence[SourceReport], apply: bool) -> str:
    lines: List[str] = []
    for r in reports:
        lines.append(f"[{r.source_id}] fetched={len(r.fetched)} skipped={len(r.skipped)} created={len(r.created)} updated={len(r.updated)} errors={len(r.errors)}")
        for d in r.fetched[:20]:
            lines.append(f"  - {d.title} ({d.url}) [{d.word_count} words]" + ("" if apply else "  [dry-run]"))
        for d in r.skipped[:10]:
            lines.append(f"  ~ skipped {d.url}: {d.skip_reason}")
        for e in r.errors[:5]:
            lines.append(f"  ! {e}")
    return "\n".join(lines)
