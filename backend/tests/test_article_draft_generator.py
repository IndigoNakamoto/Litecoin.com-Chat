"""Tests for Payload CMS article create used by knowledge-candidate publish."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_create_payload_draft_sends_service_and_user_key_headers(monkeypatch):
    monkeypatch.setenv("PAYLOAD_URL", "http://payload_cms:3000")
    monkeypatch.setenv("PAYLOAD_API_KEY", "test-service-key-123")

    from backend.services.article_draft_generator import create_payload_draft

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"doc": {"id": "art-1"}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.services.article_draft_generator.httpx.AsyncClient", return_value=mock_client):
        article_id = await create_payload_draft(
            question="What is MWEB?",
            answer="MimbleWimble Extension Block.",
            topic="privacy",
            publish_status="published",
        )

    assert article_id == "art-1"
    _args, kwargs = mock_client.post.call_args
    assert kwargs["json"]["status"] == "published"
    assert kwargs["headers"]["Authorization"] == "users API-Key test-service-key-123"
    assert kwargs["headers"]["X-Payload-Service-Key"] == "test-service-key-123"


@pytest.mark.asyncio
async def test_create_payload_draft_requires_api_key(monkeypatch):
    monkeypatch.delenv("PAYLOAD_API_KEY", raising=False)
    monkeypatch.setenv("PAYLOAD_URL", "http://payload_cms:3000")

    from backend.services.article_draft_generator import create_payload_draft

    with pytest.raises(ValueError, match="PAYLOAD_API_KEY"):
        await create_payload_draft(question="Q", answer="A")


@pytest.mark.asyncio
async def test_create_payload_article_includes_source_url(monkeypatch):
    monkeypatch.setenv("PAYLOAD_URL", "http://payload_cms:3000")
    monkeypatch.setenv("PAYLOAD_API_KEY", "test-service-key-123")

    from backend.services.article_draft_generator import create_payload_article

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"doc": {"id": "art-2"}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.services.article_draft_generator.httpx.AsyncClient", return_value=mock_client):
        article_id = await create_payload_article(
            title="What is Proof of Work",
            markdown="# What is Proof of Work\n\nBody",
            status="draft",
            source_url="https://litecoin.com/learning-center/what-is-proof-of-work",
        )

    assert article_id == "art-2"
    _args, kwargs = mock_client.post.call_args
    assert kwargs["json"]["status"] == "draft"
    assert kwargs["json"]["sourceUrl"] == "https://litecoin.com/learning-center/what-is-proof-of-work"
    assert kwargs["headers"]["X-Payload-Service-Key"] == "test-service-key-123"


@pytest.mark.asyncio
async def test_create_payload_article_retries_without_source_url(monkeypatch):
    monkeypatch.setenv("PAYLOAD_URL", "http://payload_cms:3000")
    monkeypatch.setenv("PAYLOAD_API_KEY", "test-service-key-123")

    from backend.services.article_draft_generator import create_payload_article

    bad = MagicMock()
    bad.status_code = 400
    bad.text = '{"errors":[{"message":"sourceUrl is not a valid field"}]}'
    good = MagicMock()
    good.status_code = 201
    good.json.return_value = {"doc": {"id": "art-3"}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[bad, good])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.services.article_draft_generator.httpx.AsyncClient", return_value=mock_client):
        article_id = await create_payload_article(
            title="What is Proof of Work",
            markdown="# What is Proof of Work\n\nBody",
            status="draft",
            source_url="https://litecoin.com/learning-center/what-is-proof-of-work",
        )

    assert article_id == "art-3"
    assert mock_client.post.call_count == 2
    assert "sourceUrl" not in mock_client.post.call_args_list[1].kwargs["json"]


@pytest.mark.asyncio
async def test_find_payload_article_ignores_unrelated_first_doc(monkeypatch):
    monkeypatch.setenv("PAYLOAD_URL", "http://payload_cms:3000")
    monkeypatch.setenv("PAYLOAD_API_KEY", "test-service-key-123")

    from backend.services.article_draft_generator import find_payload_article

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "docs": [{"id": "other-1", "title": {"en": "Unrelated FAQ"}, "sourceUrl": None}]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.services.article_draft_generator.httpx.AsyncClient", return_value=mock_client):
        found = await find_payload_article(
            source_url="https://litecoin.com/learning-center/what-is-proof-of-work",
            title="What is Proof-Of-Work?",
        )

    assert found is None


@pytest.mark.asyncio
async def test_create_payload_draft_403_explains_service_key(monkeypatch):
    monkeypatch.setenv("PAYLOAD_URL", "http://payload_cms:3000")
    monkeypatch.setenv("PAYLOAD_API_KEY", "test-service-key-123")

    from backend.services.article_draft_generator import create_payload_draft

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = '{"errors":[{"message":"You are not allowed to perform this action."}]}'

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.services.article_draft_generator.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="must match the CMS PAYLOAD_API_KEY"):
            await create_payload_draft(question="Q", answer="A", publish_status="published")
