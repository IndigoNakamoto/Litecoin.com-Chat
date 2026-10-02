"""Tests for the litecoin.com Learning Center scraper (no network)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.data_ingestion.litecoin_com_scraper import (
    CloudflareChallengeError,
    ExtractedPage,
    create_drafts_for_pages,
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
