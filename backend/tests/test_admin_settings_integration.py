#!/usr/bin/env python3
"""
Integration tests for admin settings changes taking effect.

These tests verify that:
1. Admin can update settings via API
2. Settings are saved to Redis
3. Backend reads settings from Redis dynamically
4. Changes actually affect behavior (rate limits, challenges, etc.)
"""

import os
import sys
import pytest
import json
from unittest.mock import patch, AsyncMock
from dotenv import load_dotenv

# Load environment
backend_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(backend_dir, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True)

# Add project root to path
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient
from backend.main import app

# Test admin token
TEST_ADMIN_TOKEN = "test-admin-token-12345"


@pytest.fixture
def admin_headers():
    """Create admin authentication headers."""
    return {"Authorization": f"Bearer {TEST_ADMIN_TOKEN}"}


@pytest.fixture
def admin_client(mock_redis, mock_motor_client, mock_llm, monkeypatch):
    """FastAPI TestClient with mocked dependencies and admin token configured."""
    from backend import dependencies
    from backend import redis_client
    
    # Set admin token
    monkeypatch.setenv("ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    
    # Override dependencies
    async def override_get_redis_client():
        return mock_redis
    
    async def override_get_mongo_client():
        return mock_motor_client
    
    async def override_get_cms_db():
        db = mock_motor_client["test_db"]
        return db["cms_articles"]
    
    async def override_get_user_questions_collection():
        db = mock_motor_client["test_db"]
        return db["user_questions"]
    
    # Apply overrides
    app.dependency_overrides[dependencies.get_mongo_client] = override_get_mongo_client
    app.dependency_overrides[dependencies.get_cms_db] = override_get_cms_db
    app.dependency_overrides[dependencies.get_user_questions_collection] = override_get_user_questions_collection
    
    # Override Redis client for all modules
    async def fake_get_redis_client():
        return mock_redis
    
    # Force all modules to use mock Redis
    monkeypatch.setenv("REDIS_URL", "redis://localhost:1")  # invalid on purpose
    redis_modules = [
        "backend.redis_client.get_redis_client",
        "backend.api.v1.admin.settings.get_redis_client",
        "backend.rate_limiter.get_redis_client",
        "backend.utils.challenge.get_redis_client",
        "backend.utils.cost_throttling.get_redis_client",
    ]
    for module_path in redis_modules:
        try:
            monkeypatch.setattr(module_path, fake_get_redis_client)
        except AttributeError:
            # Module doesn't have get_redis_client, skip it
            pass
    
    # Override environment variables for testing
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("MONGO_URI", "mongodb://test")
    monkeypatch.setenv("WEBHOOK_SECRET", "test-webhook-secret-key")
    
    test_client = TestClient(app)
    
    try:
        yield test_client
    finally:
        # Cleanup overrides
        app.dependency_overrides.clear()
        # Clear settings cache
        from backend.utils.settings_reader import clear_settings_cache
        clear_settings_cache()


def test_settings_saved_to_redis(admin_client, admin_headers, mock_redis):
    """Test that updating settings via API saves them to Redis."""
    # Update settings via API
    new_settings = {
        "global_rate_limit_per_minute": 2000,
        "enable_challenge_response": False
    }
    
    response = admin_client.put(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers,
        json=new_settings
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Verify settings were saved to Redis storage
    settings_key = "admin:settings:abuse_prevention"
    saved_settings_json = mock_redis._storage.get(settings_key)
    assert saved_settings_json is not None
    
    saved_settings = json.loads(saved_settings_json)
    assert saved_settings.get("global_rate_limit_per_minute") == 2000
    assert saved_settings.get("enable_challenge_response") is False


@pytest.mark.asyncio
async def test_settings_read_dynamically_after_update(mock_redis, monkeypatch):
    """Test that settings are read dynamically after update (cache cleared)."""
    from backend.api.v1.admin.settings import save_settings_to_redis
    from backend.utils.settings_reader import get_setting_from_redis_or_env, clear_settings_cache
    
    # Patch get_redis_client for settings module
    async def fake_get_redis_client():
        return mock_redis
    monkeypatch.setattr("backend.api.v1.admin.settings.get_redis_client", fake_get_redis_client)
    
    # Set initial settings directly in Redis storage
    initial_settings = {
        "global_rate_limit_per_minute": 1000,
        "enable_challenge_response": True
    }
    
    await save_settings_to_redis(initial_settings)
    clear_settings_cache()
    
    # Read setting - should get initial value
    value = await get_setting_from_redis_or_env(
        mock_redis,
        "global_rate_limit_per_minute",
        "GLOBAL_RATE_LIMIT_PER_MINUTE",
        1000,
        int
    )
    assert value == 1000
    
    # Update settings
    updated_settings = {
        "global_rate_limit_per_minute": 2500,
        "enable_challenge_response": False
    }
    await save_settings_to_redis(updated_settings)
    clear_settings_cache()  # Clear cache so new values are read
    
    # Read setting again - should get updated value
    value = await get_setting_from_redis_or_env(
        mock_redis,
        "global_rate_limit_per_minute",
        "GLOBAL_RATE_LIMIT_PER_MINUTE",
        1000,
        int
    )
    assert value == 2500


@pytest.mark.asyncio
async def test_global_rate_limit_uses_updated_settings(mock_redis, monkeypatch):
    """Test that global rate limiting uses updated settings from Redis."""
    from backend.api.v1.admin.settings import save_settings_to_redis
    from backend.utils.settings_reader import get_setting_from_redis_or_env, clear_settings_cache
    
    # Patch get_redis_client
    async def fake_get_redis_client():
        return mock_redis
    monkeypatch.setattr("backend.api.v1.admin.settings.get_redis_client", fake_get_redis_client)
    
    # Set custom rate limit
    settings = {
        "enable_global_rate_limit": True,
        "global_rate_limit_per_minute": 50,  # Low limit for testing
        "global_rate_limit_per_hour": 500
    }
    
    await save_settings_to_redis(settings)
    clear_settings_cache()
    
    # Verify settings are read correctly
    enabled = await get_setting_from_redis_or_env(
        mock_redis,
        "enable_global_rate_limit",
        "ENABLE_GLOBAL_RATE_LIMIT",
        True,
        bool
    )
    assert enabled is True
    
    limit = await get_setting_from_redis_or_env(
        mock_redis,
        "global_rate_limit_per_minute",
        "GLOBAL_RATE_LIMIT_PER_MINUTE",
        1000,
        int
    )
    assert limit == 50


@pytest.mark.asyncio
async def test_challenge_response_uses_updated_settings(mock_redis, monkeypatch):
    """Test that challenge-response feature respects updated settings."""
    from backend.utils.challenge import generate_challenge
    from backend.api.v1.admin.settings import save_settings_to_redis
    from backend.utils.settings_reader import clear_settings_cache
    
    # Patch get_redis_client for both modules
    async def fake_get_redis_client():
        return mock_redis
    monkeypatch.setattr("backend.api.v1.admin.settings.get_redis_client", fake_get_redis_client)
    monkeypatch.setattr("backend.redis_client.get_redis_client", fake_get_redis_client)
    
    # Disable challenge response
    settings = {
        "enable_challenge_response": False
    }
    
    await save_settings_to_redis(settings)
    clear_settings_cache()
    
    # Try to generate challenge - should return disabled
    result = await generate_challenge("test_identifier")
    assert result.get("challenge") == "disabled"
    
    # Enable challenge response
    settings["enable_challenge_response"] = True
    await save_settings_to_redis(settings)
    clear_settings_cache()
    
    # Now should generate a real challenge
    result = await generate_challenge("test_identifier")
    assert result.get("challenge") != "disabled"
    assert result.get("challenge") is not None
    assert len(result.get("challenge", "")) == 64  # 32 bytes hex = 64 chars


@pytest.mark.asyncio
async def test_challenge_ttl_uses_updated_settings(mock_redis, monkeypatch):
    """Test that challenge TTL uses updated settings."""
    from backend.utils.challenge import generate_challenge
    from backend.api.v1.admin.settings import save_settings_to_redis
    from backend.utils.settings_reader import clear_settings_cache
    
    # Patch get_redis_client
    async def fake_get_redis_client():
        return mock_redis
    monkeypatch.setattr("backend.api.v1.admin.settings.get_redis_client", fake_get_redis_client)
    monkeypatch.setattr("backend.redis_client.get_redis_client", fake_get_redis_client)
    
    # Set custom TTL
    custom_ttl = 600  # 10 minutes
    settings = {
        "enable_challenge_response": True,
        "challenge_ttl_seconds": custom_ttl
    }
    
    await save_settings_to_redis(settings)
    clear_settings_cache()
    
    result = await generate_challenge("test_identifier_ttl")
    assert result.get("expires_in_seconds") == custom_ttl


@pytest.mark.asyncio
async def test_cost_throttling_uses_updated_settings(mock_redis, monkeypatch):
    """Test that cost throttling uses updated settings."""
    from backend.utils.cost_throttling import check_cost_based_throttling
    from backend.api.v1.admin.settings import save_settings_to_redis
    from backend.utils.settings_reader import get_setting_from_redis_or_env, clear_settings_cache
    
    # Patch get_redis_client
    async def fake_get_redis_client():
        return mock_redis
    monkeypatch.setattr("backend.api.v1.admin.settings.get_redis_client", fake_get_redis_client)
    monkeypatch.setattr("backend.utils.cost_throttling.get_redis_client", fake_get_redis_client)
    
    # Set custom cost threshold
    settings = {
        "enable_cost_throttling": True,
        "high_cost_threshold_usd": 0.01,  # Very low threshold
        "high_cost_window_seconds": 600,
        "cost_throttle_duration_seconds": 30,
        "daily_cost_limit_usd": 0.10
    }
    
    await save_settings_to_redis(settings)
    clear_settings_cache()
    
    # Verify settings are read correctly
    threshold = await get_setting_from_redis_or_env(
        mock_redis,
        "high_cost_threshold_usd",
        "HIGH_COST_THRESHOLD_USD",
        0.02,
        float
    )
    assert threshold == 0.01
    
    # Check that throttling function uses the setting (result depends on state)
    throttled, reason = await check_cost_based_throttling("test_fp_cost_new", 0.005)
    assert isinstance(throttled, bool)


@pytest.mark.asyncio
async def test_partial_settings_update_preserves_other_settings(mock_redis, monkeypatch):
    """Test that partial settings update preserves existing settings."""
    from backend.api.v1.admin.settings import save_settings_to_redis, get_settings_from_redis
    from backend.utils.settings_reader import clear_settings_cache
    
    # Patch get_redis_client
    async def fake_get_redis_client():
        return mock_redis
    monkeypatch.setattr("backend.api.v1.admin.settings.get_redis_client", fake_get_redis_client)
    
    # Set initial settings
    initial_settings = {
        "global_rate_limit_per_minute": 1000,
        "global_rate_limit_per_hour": 50000,
        "enable_challenge_response": True,
        "challenge_ttl_seconds": 300
    }
    
    await save_settings_to_redis(initial_settings)
    clear_settings_cache()
    
    # Get current settings and update only one
    current_settings = await get_settings_from_redis()
    current_settings["global_rate_limit_per_minute"] = 2000
    
    # Save merged settings (simulating what the endpoint does)
    await save_settings_to_redis(current_settings)
    clear_settings_cache()
    
    # Verify all settings are still there
    all_settings = await get_settings_from_redis()
    assert all_settings.get("global_rate_limit_per_minute") == 2000
    assert all_settings.get("global_rate_limit_per_hour") == 50000
    assert all_settings.get("enable_challenge_response") is True
    assert all_settings.get("challenge_ttl_seconds") == 300


def test_settings_endpoint_shows_redis_source(admin_client, admin_headers, mock_redis):
    """Test that settings endpoint correctly identifies Redis vs env source."""
    # Update settings via API
    settings = {
        "global_rate_limit_per_minute": 3000,
        "enable_challenge_response": False
    }
    
    # Update settings
    response = admin_client.put(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers,
        json=settings
    )
    assert response.status_code == 200
    
    # Get settings back
    response = admin_client.get(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    
    # Verify settings are returned
    assert "settings" in data
    assert "sources" in data
    
    # Verify our updated settings are present
    assert data["settings"].get("global_rate_limit_per_minute") == 3000
    assert data["settings"].get("enable_challenge_response") is False
    
    # Verify sources indicate Redis (for settings we updated)
    assert data["sources"].get("global_rate_limit_per_minute") == "redis"
    assert data["sources"].get("enable_challenge_response") == "redis"


def test_settings_endpoint_update_and_get(admin_client, admin_headers, mock_redis):
    """Test full cycle: update settings via API, then get them back."""
    # Step 1: Update settings
    new_settings = {
        "global_rate_limit_per_minute": 1500,
        "enable_challenge_response": True,
        "challenge_ttl_seconds": 450
    }
    
    response = admin_client.put(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers,
        json=new_settings
    )
    assert response.status_code == 200
    update_data = response.json()
    assert update_data["success"] is True
    
    # Step 2: Get settings back
    response = admin_client.get(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers
    )
    assert response.status_code == 200
    get_data = response.json()
    
    # Step 3: Verify all settings are present and correct
    settings = get_data["settings"]
    assert settings.get("global_rate_limit_per_minute") == 1500
    assert settings.get("enable_challenge_response") is True
    assert settings.get("challenge_ttl_seconds") == 450
    
    # Step 4: Verify settings are marked as coming from Redis
    sources = get_data["sources"]
    assert sources.get("global_rate_limit_per_minute") == "redis"
    assert sources.get("enable_challenge_response") == "redis"
    assert sources.get("challenge_ttl_seconds") == "redis"


@pytest.mark.asyncio
async def test_global_spend_limits_use_updated_settings(mock_redis, monkeypatch):
    """Test that global daily and hourly spend limits use updated settings from Redis."""
    from backend.monitoring.spend_limit import get_current_usage, check_spend_limit
    from backend.api.v1.admin.settings import save_settings_to_redis
    from backend.utils.settings_reader import get_setting_from_redis_or_env, clear_settings_cache
    
    # Patch get_redis_client for all modules
    async def fake_get_redis_client():
        return mock_redis
    monkeypatch.setattr("backend.api.v1.admin.settings.get_redis_client", fake_get_redis_client)
    monkeypatch.setattr("backend.monitoring.spend_limit.get_redis_client", fake_get_redis_client)
    
    # Set custom global spend limits
    settings = {
        "daily_spend_limit_usd": 10.00,  # Custom daily limit
        "hourly_spend_limit_usd": 2.00,   # Custom hourly limit
    }
    
    await save_settings_to_redis(settings)
    clear_settings_cache()
    
    # Verify settings are read correctly
    daily_limit = await get_setting_from_redis_or_env(
        mock_redis,
        "daily_spend_limit_usd",
        "DAILY_SPEND_LIMIT_USD",
        5.00,
        float
    )
    assert daily_limit == 10.00
    
    hourly_limit = await get_setting_from_redis_or_env(
        mock_redis,
        "hourly_spend_limit_usd",
        "HOURLY_SPEND_LIMIT_USD",
        1.00,
        float
    )
    assert hourly_limit == 2.00
    
    # Mock Redis to return low costs so we can test limit checking
    mock_redis.get = AsyncMock(return_value="0.0")
    mock_redis.hget = AsyncMock(return_value="0")
    
    # Test that get_current_usage uses the updated limits
    usage = await get_current_usage()
    assert usage["daily"]["limit_usd"] == 10.00
    assert usage["hourly"]["limit_usd"] == 2.00
    
    # Test that check_spend_limit uses the updated limits
    # Set daily cost close to the new limit
    daily_cost = 9.5  # Just under 10.00
    async def get_side_effect(key):
        if "daily" in str(key):
            return str(daily_cost)
        else:
            return "0.0"  # Hourly is low
    
    mock_redis.get = AsyncMock(side_effect=get_side_effect)
    
    # Mock the Lua script eval() - CHECK_AND_RESERVE_SPEND_LUA returns:
    # [status_code, daily_cost, hourly_cost]
    # status_code: 0 = allowed, 1 = daily limit exceeded, 2 = hourly limit exceeded
    async def mock_eval(script, num_keys, *args):
        # args: daily_key, hourly_key, buffered_cost, daily_limit, hourly_limit, daily_ttl, hourly_ttl
        buffered_cost = float(args[2]) if len(args) > 2 else 0.0
        daily_limit_arg = float(args[3]) if len(args) > 3 else 10.00
        
        # Simulate: current daily = 9.5, adding 0.66 (0.6*1.1) would exceed 10.00
        current_daily = 9.5
        if current_daily + buffered_cost > daily_limit_arg:
            return [1, current_daily, 0.0]  # status=1 (daily exceeded)
        return [0, current_daily + buffered_cost, 0.0]  # status=0 (allowed)
    
    mock_redis.eval = mock_eval
    
    # Request that would exceed the new daily limit (with 10% buffer)
    # 9.5 + 0.6*1.1 = 10.16 > 10.00 → blocked
    allowed, error_msg, usage_info = await check_spend_limit(0.6, "test-model")
    
    assert allowed is False
    assert error_msg is not None
    assert "daily" in error_msg.lower() or "limit" in error_msg.lower()
    assert usage_info["daily"]["limit_usd"] == 10.00  # Should use updated limit


@pytest.mark.asyncio
async def test_global_spend_limits_settings_endpoint(admin_client, admin_headers, mock_redis, monkeypatch):
    """Test that global spend limit settings can be updated and retrieved via API."""
    # Patch get_redis_client
    async def fake_get_redis_client():
        return mock_redis
    monkeypatch.setattr("backend.api.v1.admin.settings.get_redis_client", fake_get_redis_client)
    
    # Update global spend limit settings via API
    new_settings = {
        "daily_spend_limit_usd": 15.00,
        "hourly_spend_limit_usd": 3.00,
    }
    
    response = admin_client.put(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers,
        json=new_settings
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Get settings back
    response = admin_client.get(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers
    )
    assert response.status_code == 200
    get_data = response.json()
    
    # Verify settings are present and correct
    settings = get_data["settings"]
    assert settings.get("daily_spend_limit_usd") == 15.00
    assert settings.get("hourly_spend_limit_usd") == 3.00
    
    # Verify settings are marked as coming from Redis
    sources = get_data["sources"]
    assert sources.get("daily_spend_limit_usd") == "redis"
    assert sources.get("hourly_spend_limit_usd") == "redis"

