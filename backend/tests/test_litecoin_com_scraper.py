"""Tests for the litecoin.com Learning Center scraper (no network)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_ingestion.litecoin_com_scraper import (
    SECTION_PROJECTS,
    CloudflareChallengeError,
    ExtractedPage,
    create_drafts_for_pages,
    discover_urls,
    discovery_seeds,
    extract_links,
    extract_page,
    format_draft_markdown,
    is_cloudflare_challenge,
    is_discovery_hub,
    is_ingestible_url,
    parse_sitemap_locs,
)


ARTICLE_PARAGRAPH = (
    "Litecoin is a peer-to-peer cryptocurrency that uses Scrypt proof of work "
    "and targets a two and a half minute block interval. "
) * 20  # well over the thin-page threshold


ARTICLE_HTML = f"""<!DOCTYPE html>
<html>
<head>
  <title>What is Proof of Work | Litecoin</title>
  <meta property="og:title" content="What is Proof of Work" />
</head>
<body>
  <nav>
    <a href="https://litecoin.com/buy">Buy</a>
    <a href="https://litecoin.com/learning-center/how-to-mine-litecoin">Mine</a>
  </nav>
  <header>Litecoin Learning Center</header>
  <main>
    <article>
      <h1>What is Proof of Work</h1>
      <p>{ARTICLE_PARAGRAPH}</p>
      <h2>How it works</h2>
      <p>Miners compete to find a hash below a target difficulty.</p>
      <ul>
        <li>Scrypt</li>
        <li>Blocks every 2.5 minutes</li>
      </ul>
    </article>
  </main>
  <footer>Copyright Litecoin Foundation</footer>
</body>
</html>
"""

THIN_HTML = """<!DOCTYPE html>
<html>
<head><title>Video</title></head>
<body>
  <main>
    <article>
      <h1>Watch this video</h1>
      <p>A short clip.</p>
    </article>
  </main>
</body>
</html>
"""

CF_HTML = """<!DOCTYPE html>
<html>
<body>
  <h1>litecoin.com</h1>
  <h2>Performing security verification</h2>
  <p>Enable JavaScript and cookies to continue</p>
  <p>Ray ID: a32deeaa6acb23d0</p>
</body>
</html>
"""

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://litecoin.com/learning-center/what-is-proof-of-work</loc></url>
  <url><loc>https://litecoin.com/buy</loc></url>
  <url><loc>https://litecoin.com/learning-center/learning-center</loc></url>
</urlset>
"""


PROJECT_BODY = (
    "LitecoinSpace.org has adapted the Mempool Space code from Bitcoin for Litecoin users, "
    "with a strong emphasis on the transaction fee market. "
) * 12

# Mirrors the real template: <title> is the bare slug, the listing title is the hero
# `article > header > h1`, footer social headings are h1s in plain divs, and the body is
# article > div.content > div.markdown (outer, wrapping the Info / Links / Share widgets
# and the Contributors list) > div.markdown (inner). Funding counters sit in an aside.
PROJECT_HTML = f"""<!DOCTYPE html>
<html>
<head>
  <title>litecoin-space-mempool</title>
</head>
<body>
  <nav><a href="https://litecoin.com/projects">Projects</a></nav>
  <div><div><h1>LITECOIN SOCIALS</h1><a href="https://twitter.com/litecoin">Twitter</a></div></div>
  <article>
    <header><h1>Litecoin Space Mempool Explorer</h1></header>
    <div class="content">
      <div class="markdown">
        <div>
          <h2>Info</h2>
          <div class="flex">
            <div>Links:</div>
            <a href="https://litecoinspace.org/">litecoinspace.org/</a>
            <a href="https://github.com/litecoin-foundation/ltcspace">Github</a>
            <a href="http://reddit.com/r/litecoin">/r/litecoin</a>
            <a href="https://litecoin.com/how-donations-work">How Donations Work</a>
            <div>Share:</div>
            <a href="#">Copy link</a>
            <a href="https://twitter.com/intent/tweet?text=x">x</a>
            <a href="https://www.facebook.com/sharer/sharer.php?u=">facebook</a>
          </div>
          <div class="markdown">
            <h2>Litecoin Mempool Explorer: A Comprehensive Guide</h2>
            <p>{PROJECT_BODY}</p>
            <p>\u200d</p>
            <ul><li><strong>Insight into the fee market</strong>: helps users set fees.</li></ul>
          </div>
          <div class="mt-8"><h2>Contributors</h2><p>Loshan T</p></div>
        </div>
      </div>
    </div>
    <aside>
      <h3>Funding Summary</h3><h4>0</h4><h4>Number of Donations</h4>
      <h4>Ł 19.03</h4><h4>Community Raised (LTC)</h4>
      <h3>Impact Summary</h3><h4>Ł 19.03 + $ 5,407.22</h4><h4>Paid to Contributors</h4>
      <button>DONATE</button>
    </aside>
  </article>
  <footer>Copyright Litecoin Foundation</footer>
</body>
</html>
"""

PROJECTS_HUB_HTML = """<html><body><main>
  <h1>Litecoin Projects</h1>
  <a href="https://litecoin.com/projects/litecoin-space-mempool">Litecoin Space Mempool Explorer</a>
  <a href="/projects/litecoin-dev-kit">Litecoin Development Kit</a>
  <a href="/projects/submit">Submit Project</a>
  <a href="/learning-center/what-is-proof-of-work">Learn</a>
  <a href="https://litecoin.com/projects">View projects</a>
</main></body></html>"""


def test_projects_allowlist_is_section_scoped():
    ldk = "https://litecoin.com/projects/litecoin-dev-kit"
    # Default (Learning Center) behaviour is unchanged: project pages are not articles.
    assert not is_ingestible_url(ldk)
    assert is_ingestible_url(ldk, section=SECTION_PROJECTS)
    assert is_ingestible_url("https://www.litecoin.com/projects/ordinals-lite/", section=SECTION_PROJECTS)
    # Hub, proposal form, other sections and other hosts are rejected for the projects section.
    assert not is_ingestible_url("https://litecoin.com/projects", section=SECTION_PROJECTS)
    assert not is_ingestible_url("https://litecoin.com/projects/submit", section=SECTION_PROJECTS)
    assert not is_ingestible_url("https://litecoin.com/projects-backup", section=SECTION_PROJECTS)
    assert not is_ingestible_url("https://litecoin.com/learning-center/what-is-proof-of-work", section=SECTION_PROJECTS)
    assert not is_ingestible_url("https://litecoinspace.org/projects/x", section=SECTION_PROJECTS)
    assert is_discovery_hub("https://litecoin.com/projects", section=SECTION_PROJECTS)
    assert not is_discovery_hub("https://litecoin.com/projects", )
    assert discovery_seeds(SECTION_PROJECTS) == ("https://litecoin.com/projects",)
    with pytest.raises(ValueError, match="Unknown litecoin.com section"):
        is_ingestible_url(ldk, section="blog")


def test_extract_project_page_keeps_body_and_strips_funding_widgets():
    url = "https://litecoin.com/projects/litecoin-space-mempool"
    page = extract_page(url, PROJECT_HTML, section=SECTION_PROJECTS)

    assert page.skip_reason is None
    assert page.title == "Litecoin Space Mempool Explorer"
    assert page.markdown.startswith("# Litecoin Space Mempool Explorer")
    assert "## Litecoin Mempool Explorer: A Comprehensive Guide" in page.markdown
    assert "transaction fee market" in page.markdown
    assert "- Insight into the fee market: helps users set fees." in page.markdown
    # Widgets and counters are gone.
    for leaked in ("Info", "Links:", "Share:", "Copy link", "facebook", "How Donations Work",
                   "Contributors", "Loshan T", "Funding Summary", "Impact Summary",
                   "Number of Donations", "Ł 19.03", "5,407.22", "DONATE", "LITECOIN SOCIALS"):
        assert leaked not in page.markdown, leaked
    # The project's own links are kept as a short trailing section; share intents are not.
    assert "## Project links" in page.markdown
    assert "- [litecoinspace.org](https://litecoinspace.org/)" in page.markdown
    assert "- [Github](https://github.com/litecoin-foundation/ltcspace)" in page.markdown
    assert "twitter.com" not in page.markdown and "reddit.com" not in page.markdown
    assert f"Imported from [{url}]({url})" in page.markdown
    # The same HTML is not an article for the default section.
    assert extract_page(url, PROJECT_HTML).skip_reason == "not_allowlisted"


def test_extract_project_page_without_markdown_block_falls_back_to_content_root():
    html = f"""<html><head><title>Litecoin Core | Litecoin</title></head>
    <body><main><h2>Run a node</h2><p>{PROJECT_BODY}</p><h3>Funding Summary</h3><h4>$ 0.00</h4></main></body></html>"""
    page = extract_page("https://litecoin.com/projects/core", html, section=SECTION_PROJECTS)
    assert page.skip_reason is None
    assert "## Run a node" in page.markdown
    assert "Funding Summary" not in page.markdown and "$ 0.00" not in page.markdown


@pytest.mark.asyncio
async def test_discover_urls_for_projects_uses_hub_links_only():
    class _Fetcher:
        def __init__(self):
            self.calls = []

        async def get_text(self, url):
            self.calls.append(url)
            if url.endswith("sitemap.xml"):
                return SITEMAP_XML
            return PROJECTS_HUB_HTML

    fetcher = _Fetcher()
    urls = await discover_urls(fetcher, section=SECTION_PROJECTS)
    assert urls == [
        "https://litecoin.com/projects/litecoin-dev-kit",
        "https://litecoin.com/projects/litecoin-space-mempool",
    ]
    assert "https://litecoin.com/projects" in fetcher.calls
    assert not any("learningcenter" in c for c in fetcher.calls)


def test_allowlist_accepts_learning_center_article():
    assert is_ingestible_url("https://litecoin.com/learning-center/what-is-proof-of-work")
    assert is_ingestible_url("https://www.litecoin.com/learning-center/what-is-proof-of-work#section")
    assert is_ingestible_url("https://litecoin.com/what-is-litecoin")


def test_allowlist_rejects_hub_and_marketing_pages():
    assert not is_ingestible_url("https://litecoin.com/buy")
    assert not is_ingestible_url("https://litecoin.com/learning-center/learning-center")
    assert not is_ingestible_url("https://litecoin.com/learningcenter")
    assert not is_ingestible_url("https://litecoin.com/news")
    assert is_discovery_hub("https://litecoin.com/learningcenter")
    assert is_discovery_hub("https://litecoin.com/learning-center/learning-center/")


def test_title_prefers_slug_matching_h1_over_generic_title_tag():
    html = f"""<!DOCTYPE html>
    <html><head><title>Litecoin</title></head>
    <body>
      <h1>What is Proof-Of-Work?</h1>
      <p>{ARTICLE_PARAGRAPH}</p>
      <h1>Why Litecoin?</h1>
      <p>Another card.</p>
    </body></html>
    """
    page = extract_page("https://litecoin.com/learning-center/what-is-proof-of-work", html)
    assert page.title == "What is Proof-Of-Work?"
    assert page.skip_reason is None


def test_extract_drops_learning_center_catalog_and_keeps_article():
    html = f"""<!DOCTYPE html>
    <html><head><title>Litecoin</title></head>
    <body>
      <main>
        <h1>The importance of financial privacy with Jon Moore</h1>
        <h1>URI Schemes</h1>
        <h1>Proof of Work</h1>
        <h1>Why Litecoin?</h1>
        <a href="https://litecoin.com/learning-center/why-litecoin">Why Litecoin?</a>
        <h1>Proof of Work</h1>
        <p>{ARTICLE_PARAGRAPH}</p>
        <h3>Scrypt during mining</h3>
        <p>Miners hash the 80-byte header until it is below the target.</p>
        <h1>Why Litecoin?</h1>
      </main>
    </body></html>
    """
    page = extract_page("https://litecoin.com/learning-center/proof-of-work", html)

    assert page.skip_reason is None
    assert page.title == "Proof of Work"
    assert "Scrypt" in page.markdown or "two and a half minute" in page.markdown
    assert "URI Schemes" not in page.markdown
    assert "Why Litecoin?" not in page.markdown
    assert "financial privacy with Jon Moore" not in page.markdown


def test_extract_strips_chrome_and_keeps_headings():
    page = extract_page("https://litecoin.com/learning-center/what-is-proof-of-work", ARTICLE_HTML)

    assert page.skip_reason is None
    assert page.title == "What is Proof of Work"
    assert "# What is Proof of Work" in page.markdown
    assert "## How it works" in page.markdown
    assert "- Scrypt" in page.markdown
    assert "Buy" not in page.markdown
    assert "Copyright Litecoin Foundation" not in page.markdown
    assert "https://litecoin.com/learning-center/what-is-proof-of-work" in page.markdown
    assert page.word_count >= 200


def test_extract_skips_thin_pages():
    page = extract_page("https://litecoin.com/learning-center/watch-this-video", THIN_HTML)

    assert page.skip_reason == "thin"
    assert page.word_count < 200


def test_extract_rejects_non_allowlisted_url():
    page = extract_page("https://litecoin.com/buy", ARTICLE_HTML)
    assert page.skip_reason == "not_allowlisted"


def test_cloudflare_challenge_is_hard_failure():
    assert is_cloudflare_challenge(CF_HTML)
    with pytest.raises(CloudflareChallengeError, match="Cloudflare challenge"):
        extract_page("https://litecoin.com/learning-center/what-is-proof-of-work", CF_HTML)


def test_extract_links_and_sitemap_locs():
    links = extract_links(ARTICLE_HTML, "https://litecoin.com/learningcenter")
    assert "https://litecoin.com/learning-center/how-to-mine-litecoin" in links
    assert "https://litecoin.com/buy" in links

    pages, children = parse_sitemap_locs(SITEMAP_XML)
    assert children == []
    assert "https://litecoin.com/learning-center/what-is-proof-of-work" in pages
    assert "https://litecoin.com/buy" in pages


def test_format_draft_markdown_does_not_duplicate_heading():
    body = "# What is Proof of Work\n\nBody text."
    result = format_draft_markdown("What is Proof of Work", body, "https://litecoin.com/learning-center/x")
    assert result.startswith("# What is Proof of Work")
    assert result.count("# What is Proof of Work") == 1
    assert "Imported from" in result


@pytest.mark.asyncio
async def test_rate_limited_client_raises_without_browser_fallback():
    from backend.data_ingestion.litecoin_com_scraper import RateLimitedClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = CF_HTML
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    fetcher = RateLimitedClient(mock_http, delay_seconds=0, use_browser_fallback=False)
    with pytest.raises(CloudflareChallengeError, match="Cloudflare challenge"):
        await fetcher.get_text("https://litecoin.com/learning-center/what-is-proof-of-work")


@pytest.mark.asyncio
async def test_apply_posts_draft_with_service_key_headers(monkeypatch):
    monkeypatch.setenv("PAYLOAD_URL", "http://payload_cms:3000")
    monkeypatch.setenv("PAYLOAD_API_KEY", "test-service-key-123")

    page = ExtractedPage(
        url="https://litecoin.com/learning-center/what-is-proof-of-work",
        title="What is Proof of Work",
        markdown="# What is Proof of Work\n\nBody",
        word_count=250,
    )

    get_response = MagicMock()
    get_response.status_code = 200
    get_response.json.return_value = {"docs": []}

    post_response = MagicMock()
    post_response.status_code = 201
    post_response.json.return_value = {"doc": {"id": "art-99"}}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=get_response)
    mock_client.post = AsyncMock(return_value=post_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.data_ingestion.litecoin_com_scraper.httpx.AsyncClient", return_value=mock_client):
        report = await create_drafts_for_pages([page])

    assert report.article_ids == ["art-99"]
    assert len(report.created) == 1
    _args, kwargs = mock_client.post.call_args
    assert kwargs["json"]["status"] == "draft"
    assert kwargs["json"]["title"] == "What is Proof of Work"
    assert kwargs["json"]["sourceUrl"] == page.url
    assert kwargs["headers"]["Authorization"] == "users API-Key test-service-key-123"
    assert kwargs["headers"]["X-Payload-Service-Key"] == "test-service-key-123"


@pytest.mark.asyncio
async def test_apply_updates_existing_article_and_deletes_extra(monkeypatch):
    monkeypatch.setenv("PAYLOAD_URL", "http://payload_cms:3000")
    monkeypatch.setenv("PAYLOAD_API_KEY", "test-service-key-123")

    page = ExtractedPage(
        url="https://litecoin.com/learning-center/what-is-proof-of-work",
        title="What is Proof of Work",
        markdown="# What is Proof of Work\n\nClean body",
        word_count=250,
    )

    get_response = MagicMock()
    get_response.status_code = 200
    get_response.json.return_value = {
        "docs": [
            {"id": "existing-1", "sourceUrl": page.url, "title": page.title},
            {"id": "existing-2", "sourceUrl": page.url, "title": page.title},
        ]
    }

    patch_response = MagicMock()
    patch_response.status_code = 200
    patch_response.json.return_value = {"doc": {"id": "existing-1"}}

    delete_response = MagicMock()
    delete_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=get_response)
    mock_client.patch = AsyncMock(return_value=patch_response)
    mock_client.delete = AsyncMock(return_value=delete_response)
    mock_client.post = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.data_ingestion.litecoin_com_scraper.httpx.AsyncClient", return_value=mock_client):
        report = await create_drafts_for_pages([page])

    assert report.created == []
    assert [item.title for item in report.updated] == [page.title]
    assert report.article_ids == ["existing-1"]
    mock_client.post.assert_not_called()
    mock_client.patch.assert_called_once()
    mock_client.delete.assert_called_once()
    assert "existing-2" in mock_client.delete.call_args.args[0]
