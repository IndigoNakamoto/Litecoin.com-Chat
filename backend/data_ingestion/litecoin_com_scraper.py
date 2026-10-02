"""
Discover educational pages on litecoin.com and convert them to markdown.

Used by the operator CLI to create Payload CMS drafts. Nothing is published
or embedded until an editor reviews the draft in the CMS.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Set
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger(__name__)

SITE_ORIGIN = "https://litecoin.com"
SITEMAP_URL = f"{SITE_ORIGIN}/sitemap.xml"
DISCOVERY_SEEDS = (
    f"{SITE_ORIGIN}/learningcenter",
    f"{SITE_ORIGIN}/learning-center/learning-center",
)
STANDALONE_PATHS = frozenset({"/what-is-litecoin"})
HUB_PATHS = frozenset({"/learningcenter", "/learning-center/learning-center"})
ALLOWED_HOSTS = frozenset({"litecoin.com", "www.litecoin.com"})
MIN_WORD_COUNT = 50
DEFAULT_REQUEST_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

CF_MARKERS = (
    "performing security verification",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
    "cf-browser-verification",
    "just a moment...",
    "attention required! | cloudflare",
)

CHROME_TAGS = (
    "nav",
    "header",
    "footer",
    "form",
    "script",
    "style",
    "noscript",
    "iframe",
    "aside",
    "template",
    "button",
)
CHROME_CLASS_FRAGMENTS = ("w-nav", "navbar", "nav-menu", "w-form")


class CloudflareChallengeError(RuntimeError):
    """litecoin.com returned a Cloudflare interstitial instead of page HTML."""


@dataclass
class ExtractedPage:
    url: str
    title: str = ""
    markdown: str = ""
    word_count: int = 0
    skip_reason: Optional[str] = None


@dataclass
class IngestReport:
    discovered: List[str] = field(default_factory=list)
    extracted: List[ExtractedPage] = field(default_factory=list)
    skipped: List[ExtractedPage] = field(default_factory=list)
    created: List[ExtractedPage] = field(default_factory=list)
    updated: List[ExtractedPage] = field(default_factory=list)
    article_ids: List[str] = field(default_factory=list)
    written: List[tuple] = field(default_factory=list)


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    scheme = "https" if parsed.scheme in ("http", "https", "") else parsed.scheme
    return urlunparse((scheme, host, path, "", "", ""))


def is_discovery_hub(url: str) -> bool:
    parsed = urlparse(normalize_url(url))
    return parsed.path in HUB_PATHS


def is_ingestible_url(url: str) -> bool:
    """True for individual Learning Center articles and standalone docs pages."""
    try:
        parsed = urlparse(normalize_url(url))
    except ValueError:
        return False
    if parsed.netloc not in ALLOWED_HOSTS and parsed.netloc != "litecoin.com":
        return False
    path = parsed.path or "/"
    if path in STANDALONE_PATHS:
        return True
    if path in HUB_PATHS:
        return False
    parts = path.split("/")
    # ['', 'learning-center', 'slug']
    if len(parts) == 3 and parts[1] == "learning-center" and parts[2] and parts[2] != "learning-center":
        return True
    return False


def is_cloudflare_challenge(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in CF_MARKERS)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def is_thin_page(text: str, min_words: int = MIN_WORD_COUNT) -> bool:
    return word_count(text) < min_words


def extract_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    found: List[str] = []
    seen: Set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute = normalize_url(urljoin(base_url, href))
        if absolute in seen:
            continue
        seen.add(absolute)
        found.append(absolute)
    return found


def parse_sitemap_locs(xml_text: str) -> tuple[List[str], List[str]]:
    """Return (page_urls, child_sitemap_urls) from a sitemap or sitemap index."""
    soup = BeautifulSoup(xml_text, "lxml-xml")
    if soup.find("sitemapindex"):
        child_sitemaps = [_text(loc) for loc in soup.find_all("loc") if _text(loc)]
        return [], child_sitemaps
    page_urls = [_text(loc) for loc in soup.find_all("loc") if _text(loc)]
    return page_urls, []


def _text(node: Optional[Tag]) -> str:
    if node is None:
        return ""
    return node.get_text(" ", strip=True)


def extract_page(url: str, html: str, min_words: int = MIN_WORD_COUNT) -> ExtractedPage:
    """Parse HTML into markdown. Sets skip_reason for CF or thin pages."""
    normalized = normalize_url(url)
    if is_cloudflare_challenge(html):
        raise CloudflareChallengeError(
            f"Cloudflare challenge page received for {normalized}. "
            "Run this script from a network that can load litecoin.com in a browser."
        )
    if not is_ingestible_url(normalized):
        return ExtractedPage(url=normalized, skip_reason="not_allowlisted")

    soup = BeautifulSoup(html, "lxml")
    title = _page_title(soup, url=normalized)
    catalog = _catalog_titles(soup, normalized)
    _strip_chrome(soup)
    body = _extract_article_markdown(soup, title=title, catalog=catalog)
    body = _drop_catalog_lines(body, catalog, title)
    body = re.sub(r"\n{3,}", "\n\n", body)
    count = word_count(body)
    if is_thin_page(body, min_words=min_words):
        return ExtractedPage(
            url=normalized,
            title=title,
            markdown=body,
            word_count=count,
            skip_reason="thin",
        )
    markdown = format_draft_markdown(title, body, normalized)
    return ExtractedPage(
        url=normalized,
        title=title,
        markdown=markdown,
        word_count=count,
    )


def format_draft_markdown(title: str, body: str, source_url: str) -> str:
    body = body.strip()
    heading = f"# {title}"
    if body.startswith(heading):
        parts = [body]
    else:
        parts = [heading, "", body] if body else [heading]
    parts.extend(
        [
            "",
            "---",
            f"*Imported from [{source_url}]({source_url}). Please review and edit before publishing.*",
        ]
    )
    return "\n".join(parts)


def _strip_chrome(soup: BeautifulSoup) -> None:
    to_remove: List[Tag] = []
    for tag_name in CHROME_TAGS:
        to_remove.extend(soup.find_all(tag_name))
    for node in soup.find_all(True):
        if not isinstance(node, Tag) or node.attrs is None:
            continue
        classes = node.get("class") or []
        class_blob = " ".join(classes).lower() if isinstance(classes, list) else str(classes).lower()
        if any(fragment in class_blob for fragment in CHROME_CLASS_FRAGMENTS):
            to_remove.append(node)
    for node in to_remove:
        if node is not None and node.attrs is not None:
            node.decompose()


GENERIC_TITLES = frozenset({
    "litecoin",
    "litecoin learning center",
    "learning center",
    "untitled",
    "welcome",
})


def _title_from_slug(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return re.sub(r"[-_]+", " ", slug).strip().title()


def _slug_words(url: str) -> Set[str]:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return {part for part in re.split(r"[-_]+", slug.lower()) if part and part not in {"the", "a", "of", "and", "for"}}


def _select_content_root(soup: BeautifulSoup, title: str = "") -> Tag:
    del title  # title is used for heading text, not region selection
    for selector in ("article", "main", "[role='main']"):
        found = soup.select_one(selector)
        if found:
            return found
    body = soup.body or soup
    best_node: Tag = body
    best_len = 0
    for candidate in body.find_all(["div", "section"]):
        text_len = len(candidate.get_text(" ", strip=True))
        if text_len > best_len:
            best_node = candidate
            best_len = text_len
    return best_node


def _page_title(soup: BeautifulSoup, url: str = "") -> str:
    candidates: List[str] = []
    for heading in soup.find_all("h1"):
        text = _clean_text(heading.get_text(" ", strip=True))
        if text and text.lower() not in GENERIC_TITLES:
            candidates.append(text)
    slug_words = _slug_words(url) if url else set()
    if candidates and slug_words:
        ranked = []
        for text in candidates:
            words = set(re.findall(r"[a-z0-9]+", text.lower()))
            ranked.append((len(slug_words & words), -len(text), text))
        ranked.sort(reverse=True)
        if ranked[0][0] > 0:
            return ranked[0][2]
    if candidates:
        return candidates[0]
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        og_title = og["content"].strip()
        if og_title.lower() not in GENERIC_TITLES:
            return og_title
    if soup.title:
        raw = soup.title.get_text(" ", strip=True)
        for sep in (" | ", " – ", " - "):
            if sep in raw:
                raw = raw.split(sep, 1)[0].strip()
        if raw and raw.lower() not in GENERIC_TITLES:
            return raw
    if url:
        return _title_from_slug(url)
    return "Untitled"


def _normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _catalog_titles(soup: BeautifulSoup, page_url: str) -> Set[str]:
    titles: Set[str] = set()
    for heading in soup.find_all("h1"):
        text = _clean_text(heading.get_text(" ", strip=True))
        if text and text.lower() not in GENERIC_TITLES:
            titles.add(text)
    for anchor in soup.find_all("a", href=True):
        href = normalize_url(urljoin(page_url, anchor["href"]))
        if not is_ingestible_url(href):
            continue
        text = _clean_text(anchor.get_text(" ", strip=True))
        if text and text.lower() not in GENERIC_TITLES:
            titles.add(text)
    return titles


def _is_catalog_heading(tag: Tag, catalog: Set[str], title: str) -> bool:
    if tag.name != "h1":
        return False
    text = _clean_text(tag.get_text(" ", strip=True))
    if not text:
        return False
    if _normalize_title(text) == _normalize_title(title):
        return False
    catalog_n = {_normalize_title(item) for item in catalog}
    return _normalize_title(text) in catalog_n


def _is_catalog_block(tag: Tag) -> bool:
    if not isinstance(tag, Tag):
        return False
    class_blob = " ".join(tag.get("class") or []).lower()
    if any(token in class_blob for token in ("w-dyn-list", "collection-list", "related-articles")):
        return True
    links = tag.find_all("a", href=True)
    learning = [a for a in links if "/learning-center/" in (a.get("href") or "")]
    return len(learning) >= 5


def _take_until_catalog(siblings, catalog: Set[str], title: str) -> List[Tag]:
    blocks: List[Tag] = []
    for sibling in siblings:
        if not isinstance(sibling, Tag):
            continue
        if _is_catalog_heading(sibling, catalog, title) or _is_catalog_block(sibling):
            break
        nested_heading = sibling.find("h1") if sibling.name != "h1" else None
        if nested_heading is not None and _is_catalog_heading(nested_heading, catalog, title):
            break
        blocks.append(sibling)
    return blocks


def _heading_follow_blocks(heading: Tag, catalog: Set[str], title: str) -> List[Tag]:
    blocks = [heading]
    blocks.extend(_take_until_catalog(heading.next_siblings, catalog, title))
    follow_text = " ".join(_clean_text(block.get_text(" ", strip=True)) for block in blocks[1:])
    if word_count(follow_text) >= 80:
        return blocks
    parent = heading.parent
    if parent is not None and parent.name not in {"body", "html", "[document]"}:
        blocks.extend(_take_until_catalog(parent.next_siblings, catalog, title))
    return blocks


def _best_article_heading(soup: BeautifulSoup, title: str) -> Optional[Tag]:
    if not title or title.lower() in GENERIC_TITLES:
        return None
    want = _normalize_title(title)
    matches = [
        heading
        for heading in soup.find_all(["h1", "h2"])
        if _normalize_title(_clean_text(heading.get_text(" ", strip=True))) == want
    ]
    if not matches:
        return None
    best = matches[-1]
    best_score = -1
    for heading in matches:
        follow = " ".join(
            _clean_text(sib.get_text(" ", strip=True))
            for sib in heading.next_siblings
            if isinstance(sib, Tag)
        )
        score = word_count(follow)
        if score >= best_score:
            best = heading
            best_score = score
    return best


def _extract_article_markdown(soup: BeautifulSoup, title: str, catalog: Set[str]) -> str:
    heading = _best_article_heading(soup, title)
    if heading is not None:
        blocks = _heading_follow_blocks(heading, catalog, title)
        parts = [_element_to_markdown(block) for block in blocks]
        sliced = "\n\n".join(part for part in parts if part).strip()
        if word_count(sliced) >= 80:
            return sliced
    content_root = _select_content_root(soup, title=title)
    return _element_to_markdown(content_root).strip()


def _drop_catalog_lines(markdown: str, catalog: Set[str], title: str) -> str:
    keep = _normalize_title(title)
    catalog_n = {_normalize_title(item) for item in catalog} - {""}
    always_drop = {_normalize_title(item) for item in GENERIC_TITLES}
    kept: List[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        heading = re.sub(r"^#{1,6}\s*", "", stripped)
        link_match = re.match(r"^\[([^\]]+)\]\([^)]+\)\s*$", heading)
        text = link_match.group(1) if link_match else heading
        normalized = _normalize_title(text)
        if text and len(text.split()) <= 16 and (
            normalized in always_drop
            or normalized == keep
            or normalized in catalog_n
        ):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _clean_text(value: str) -> str:
    value = value.replace("\u200d", "").replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _inline_markdown(el: Tag) -> str:
    parts: List[str] = []
    for child in el.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        if name in ("strong", "b"):
            inner = _clean_text(_inline_markdown(child))
            parts.append(f"**{inner}**" if inner else "")
        elif name in ("em", "i"):
            inner = _clean_text(_inline_markdown(child))
            parts.append(f"*{inner}*" if inner else "")
        elif name == "a":
            href = (child.get("href") or "").strip()
            text = _clean_text(_inline_markdown(child)) or href
            if href:
                parts.append(f"[{text}]({href})")
            else:
                parts.append(text)
        elif name == "br":
            parts.append("\n")
        elif name == "code":
            parts.append(f"`{_clean_text(_inline_markdown(child))}`")
        elif name == "img":
            alt = child.get("alt") or ""
            src = child.get("src") or ""
            if src:
                parts.append(f"![{alt}]({src})")
        else:
            parts.append(_inline_markdown(child))
    return "".join(parts)


def _list_to_markdown(el: Tag, ordered: bool = False, indent: int = 0) -> str:
    lines: List[str] = []
    index = 1
    for li in el.find_all("li", recursive=False):
        nested: List[str] = []
        bits: List[str] = []
        for child in li.children:
            if isinstance(child, NavigableString):
                bits.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            if child.name in ("ul", "ol"):
                nested.append(_list_to_markdown(child, ordered=(child.name == "ol"), indent=indent + 1))
                continue
            bits.append(_inline_markdown(child))
        text = _clean_text("".join(bits))
        prefix = f"{index}. " if ordered else "- "
        lines.append(("  " * indent) + prefix + text)
        lines.extend(nested)
        index += 1
    return "\n".join(lines)


def _table_to_markdown(table: Tag) -> str:
    rows: List[List[str]] = []
    for tr in table.find_all("tr"):
        cells = [_clean_text(_inline_markdown(cell)) for cell in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header = padded[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in padded[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _element_to_markdown(el: Tag) -> str:
    name = el.name
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        text = _clean_text(_inline_markdown(el))
        return f"{'#' * int(name[1])} {text}" if text else ""
    if name == "p":
        return _clean_text(_inline_markdown(el))
    if name == "blockquote":
        inner = _clean_text(_inline_markdown(el))
        return "\n".join(f"> {line}" for line in inner.splitlines()) if inner else ""
    if name in ("ul", "ol"):
        return _list_to_markdown(el, ordered=(name == "ol"))
    if name == "table":
        return _table_to_markdown(el)
    if name == "pre":
        return f"```\n{el.get_text()}\n```"
    if name in ("div", "section", "article", "main", "body", "html", "[document]"):
        parts = [
            _element_to_markdown(child)
            for child in el.children
            if isinstance(child, Tag)
        ]
        return "\n\n".join(part for part in parts if part)
    return _clean_text(_inline_markdown(el))


class RateLimitedClient:
    """httpx wrapper that spaces requests and retries Cloudflare pages in Playwright."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        use_browser_fallback: bool = True,
    ) -> None:
        self._client = client
        self._delay = delay_seconds
        self._use_browser_fallback = use_browser_fallback
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._playwright = None
        self._browser = None
        self._context = None

    async def get_text(self, url: str) -> str:
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            wait = self._delay - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            response = await self._client.get(url)
            self._last_request_at = loop.time()
            response.raise_for_status()
            text = response.text
            if not is_cloudflare_challenge(text):
                return text
            if not self._use_browser_fallback:
                raise CloudflareChallengeError(
                    f"Cloudflare challenge page received for {url}. "
                    "Run this script from a network that can load litecoin.com in a browser."
                )
            logger.info("Cloudflare challenge for %s; retrying with Playwright", url)
            return await self._get_text_browser(url)

    async def _ensure_browser(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise CloudflareChallengeError(
                "Cloudflare blocked httpx and Playwright is not installed. "
                "Install with: python3 -m pip install playwright && python3 -m playwright install chromium"
            ) from exc
        self._playwright = await async_playwright().start()
        launch_args = ["--disable-blink-features=AutomationControlled"]
        try:
            self._browser = await self._playwright.chromium.launch(
                channel="chrome",
                headless=True,
                args=launch_args,
            )
            logger.info("Playwright using system Chrome")
        except Exception as exc:
            logger.warning("System Chrome unavailable (%s); falling back to bundled Chromium", exc)
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=launch_args,
            )
        self._context = await self._browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )

    async def _get_text_browser(self, url: str) -> str:
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            html = await _wait_for_challenge_clear(page)
            return html
        finally:
            await page.close()

    async def aclose(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


async def _wait_for_challenge_clear(page, timeout_seconds: float = 45.0) -> str:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_seconds
    html = await page.content()
    while is_cloudflare_challenge(html):
        if loop.time() >= deadline:
            raise CloudflareChallengeError(
                f"Cloudflare challenge did not clear for {page.url}. "
                "Try running from a network that can load litecoin.com in a browser."
            )
        await asyncio.sleep(1.0)
        html = await page.content()
    return html


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )


async def discover_urls(
    fetcher: RateLimitedClient,
    seeds: Sequence[str] = DISCOVERY_SEEDS,
    sitemap_url: str = SITEMAP_URL,
) -> List[str]:
    discovered: Set[str] = set()

    try:
        sitemap_xml = await fetcher.get_text(sitemap_url)
        page_urls, child_sitemaps = parse_sitemap_locs(sitemap_xml)
        for child in child_sitemaps:
            try:
                child_xml = await fetcher.get_text(child)
            except (httpx.HTTPError, CloudflareChallengeError) as exc:
                logger.warning("Skipping child sitemap %s: %s", child, exc)
                continue
            child_pages, _nested = parse_sitemap_locs(child_xml)
            page_urls.extend(child_pages)
        for loc in page_urls:
            if is_ingestible_url(loc):
                discovered.add(normalize_url(loc))
        logger.info("Sitemap contributed %d allowlisted URLs", len(discovered))
    except (httpx.HTTPError, CloudflareChallengeError) as exc:
        logger.warning("Sitemap unavailable (%s); falling back to hub-link discovery", exc)

    for seed in seeds:
        try:
            html = await fetcher.get_text(seed)
        except (httpx.HTTPError, CloudflareChallengeError) as exc:
            logger.warning("Discovery seed failed %s: %s", seed, exc)
            continue
        for link in extract_links(html, seed):
            if is_ingestible_url(link):
                discovered.add(normalize_url(link))

    urls = sorted(discovered)
    logger.info("Discovered %d ingestible URLs", len(urls))
    return urls


async def scrape_pages(
    urls: Iterable[str],
    fetcher: RateLimitedClient,
    min_words: int = MIN_WORD_COUNT,
) -> List[ExtractedPage]:
    pages: List[ExtractedPage] = []
    for url in urls:
        if not is_ingestible_url(url):
            pages.append(ExtractedPage(url=normalize_url(url), skip_reason="not_allowlisted"))
            continue
        try:
            html = await fetcher.get_text(url)
            pages.append(extract_page(url, html, min_words=min_words))
        except CloudflareChallengeError as exc:
            logger.warning("Skipping %s: %s", url, exc)
            pages.append(ExtractedPage(url=normalize_url(url), skip_reason="cloudflare"))
        except Exception as exc:
            logger.warning("Skipping %s after extract/fetch error: %s", url, exc)
            pages.append(ExtractedPage(url=normalize_url(url), skip_reason="fetch_error"))
    return pages


async def create_drafts_for_pages(pages: Sequence[ExtractedPage]) -> IngestReport:
    """Create or replace Payload drafts for extracted pages."""
    from backend.services.article_draft_generator import (
        create_payload_article,
        delete_payload_article,
        find_payload_articles,
        update_payload_article,
    )

    report = IngestReport()
    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in pages:
            if page.skip_reason:
                report.skipped.append(page)
                continue
            report.extracted.append(page)
            existing_ids = await find_payload_articles(
                source_url=page.url,
                title=page.title,
                client=client,
            )
            if existing_ids:
                article_id = await update_payload_article(
                    existing_ids[0],
                    title=page.title,
                    markdown=page.markdown,
                    status="draft",
                    source_url=page.url,
                    client=client,
                )
                for extra_id in existing_ids[1:]:
                    try:
                        await delete_payload_article(extra_id, client=client)
                    except Exception as exc:
                        logger.warning("Could not delete extra draft %s: %s", extra_id, exc)
                report.updated.append(page)
                report.article_ids.append(article_id)
                report.written.append((page, article_id, "updated"))
                continue
            article_id = await create_payload_article(
                title=page.title,
                markdown=page.markdown,
                status="draft",
                source_url=page.url,
                client=client,
            )
            report.created.append(page)
            report.article_ids.append(article_id)
            report.written.append((page, article_id, "created"))
    return report


async def run_ingest(
    *,
    apply: bool = False,
    delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
    min_words: int = MIN_WORD_COUNT,
    urls: Optional[Sequence[str]] = None,
) -> IngestReport:
    report = IngestReport()
    async with _http_client() as raw_client:
        fetcher = RateLimitedClient(raw_client, delay_seconds=delay_seconds)
        try:
            return await _run_ingest_with_fetcher(
                fetcher,
                report,
                apply=apply,
                min_words=min_words,
                urls=urls,
            )
        finally:
            await fetcher.aclose()


async def _run_ingest_with_fetcher(
    fetcher: RateLimitedClient,
    report: IngestReport,
    *,
    apply: bool,
    min_words: int,
    urls: Optional[Sequence[str]],
) -> IngestReport:
    if urls:
        discovered = [normalize_url(url) for url in urls if is_ingestible_url(url)]
        rejected = [normalize_url(url) for url in urls if not is_ingestible_url(url)]
        for url in rejected:
            report.skipped.append(ExtractedPage(url=url, skip_reason="not_allowlisted"))
    else:
        discovered = await discover_urls(fetcher)
    report.discovered = discovered
    pages = await scrape_pages(discovered, fetcher, min_words=min_words)
    for page in pages:
        if page.skip_reason:
            report.skipped.append(page)
        else:
            report.extracted.append(page)
    if apply:
        apply_report = await create_drafts_for_pages(
            [page for page in pages if not page.skip_reason]
        )
        report.created = apply_report.created
        report.updated = apply_report.updated
        report.article_ids = apply_report.article_ids
        report.written = apply_report.written
        report.skipped.extend(apply_report.skipped)
    return report


def format_report(report: IngestReport, apply: bool) -> str:
    lines = [
        f"Discovered {len(report.discovered)} ingestible URLs",
        f"Extracted {len(report.extracted)} pages",
        f"Skipped {len(report.skipped)}",
    ]
    if report.skipped:
        reasons: dict[str, int] = {}
        for page in report.skipped:
            key = page.skip_reason or "unknown"
            reasons[key] = reasons.get(key, 0) + 1
        lines.append("  skip reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())))
    if apply:
        lines.append(f"Created drafts: {len(report.created)}")
        lines.append(f"Updated drafts: {len(report.updated)}")
        written = report.written
        for page, article_id, action in written:
            lines.append(f"  - [{action}] {page.title} ({page.url}) -> {article_id} [{page.word_count} words]")
        if not written:
            lines.append("  (none)")
    else:
        lines.append("[dry-run] Would create/update drafts:")
        for page in report.extracted:
            lines.append(f"  - {page.title} ({page.url}) [{page.word_count} words]")
        if not report.extracted:
            lines.append("  (none)")
    return "\n".join(lines)
