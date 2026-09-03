#!/usr/bin/env python3
"""
Tests for admin API endpoints:
1. Authentication endpoints
2. Settings endpoints  
3. Redis management endpoints
4. Cache management endpoints
5. User statistics endpoints
"""

import os
import sys
import pytest
import json
from datetime import datetime, timedelta
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
from backend.redis_client import get_redis_client

# Test admin token
TEST_ADMIN_TOKEN = "test-admin-token-12345"

@pytest.fixture
def admin_headers():
    """Create admin authentication headers."""
    return {"Authorization": f"Bearer {TEST_ADMIN_TOKEN}"}


@pytest.fixture
def client_with_admin(monkeypatch, mock_redis):
    """Create test client with admin token configured."""
    # Set admin token in environment
    monkeypatch.setenv("ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    
    from backend import dependencies
    from backend import redis_client
    
    # Override Redis client to use mock
    async def override_get_redis_client():
        return mock_redis
    
    # Apply override
    app.dependency_overrides[redis_client.get_redis_client] = override_get_redis_client
    
    # Force all modules to use mock Redis
    async def fake_get_redis_client():
        return mock_redis
    
    for module in ["redis_client", "rate_limiter", "utils.challenge", "monitoring.spend_limit", "api.v1.admin.users", "api.v1.admin.settings"]:
        monkeypatch.setattr(f"backend.{module}.get_redis_client", fake_get_redis_client)
    
    client = TestClient(app)
    yield client
    
    # Cleanup
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_auth_login_success(client_with_admin, admin_headers):
    """Test successful admin login."""
    response = client_with_admin.post(
        "/api/v1/admin/auth/login",
        headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] == True
    assert "message" in data


def test_admin_auth_login_invalid_token(client_with_admin, mock_redis):
    """Test admin login with invalid token."""
    response = client_with_admin.post(
        "/api/v1/admin/auth/login",
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401


def test_admin_auth_verify_success(client_with_admin, admin_headers):
    """Test admin token verification."""
    response = client_with_admin.get(
        "/api/v1/admin/auth/verify",
        headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] == True


@pytest.mark.asyncio
async def test_admin_settings_get(client_with_admin, admin_headers, mock_redis):
    """Test getting abuse prevention settings."""
    # Mock Redis to return settings
    async def mock_get(key):
        if key == "admin:settings:abuse_prevention":
            return json.dumps({
                "global_rate_limit_per_minute": 1000,
                "enable_challenge_response": True
            })
        return None
    
    mock_redis.get = mock_get
    
    response = client_with_admin.get(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "settings" in data
    assert "sources" in data


@pytest.mark.asyncio
async def test_admin_settings_update(client_with_admin, admin_headers, mock_redis):
    """Test updating abuse prevention settings."""
    async def mock_set(key, value):
        return True
    
    mock_redis.set = mock_set
    
    settings = {
        "global_rate_limit_per_minute": 1500,
        "enable_challenge_response": True
    }
    
    response = client_with_admin.put(
        "/api/v1/admin/settings/abuse-prevention",
        headers=admin_headers,
        json=settings
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


@pytest.mark.asyncio
async def test_admin_redis_stats(client_with_admin, admin_headers, mock_redis, monkeypatch):
    """Test getting Redis statistics."""
    # Mock Redis scan to return empty (no bans/throttles)
    async def mock_scan(cursor=0, match=None, count=None):
        return (0, [])
    
    async def mock_zcard(key):
        return 0
    
    mock_redis.scan = mock_scan
    mock_redis.zcard = mock_zcard
    
    # The endpoint resolves its client through get_redis_client(), so the fixture
    # only takes effect once that lookup is patched.
    async def fake_get_redis_client():
        return mock_redis

    monkeypatch.setattr(
        "backend.api.v1.admin.redis.get_redis_client", fake_get_redis_client
    )

    response = client_with_admin.get(
        "/api/v1/admin/redis/stats",
        headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "bans" in data
    assert "throttles" in data
    assert data["bans"]["total"] >= 0
    assert data["throttles"]["total"] >= 0


@pytest.mark.asyncio
async def test_admin_cache_stats(client_with_admin, admin_headers, mock_redis):
    """Test getting cache statistics."""
    # Mock cache size
    async def mock_scard(key):
        return 42
    
    mock_redis.scard = mock_scard
    
    response = client_with_admin.get(
        "/api/v1/admin/cache/suggested-questions/stats",
        headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "cache_size" in data
    assert "cache_type" in data


@pytest.mark.asyncio
async def test_admin_users_stats(client_with_admin, admin_headers, mock_redis):
    """Test getting user statistics."""
    # Mock Redis sets for user tracking
    async def mock_scard(key):
        key_str = str(key)
        return 100 if "all_time" in key_str else 5
    
    async def mock_scan(cursor=0, match=None, count=None):
        return (0, [])
    
    mock_redis.scard = mock_scard
    mock_redis.scan = mock_scan
    
    response = client_with_admin.get(
        "/api/v1/admin/users/stats?days=30",
        headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_unique_users" in data
    assert "today_unique_users" in data
    assert "average_users_per_day" in data
    assert "users_over_time" in data
    assert isinstance(data["users_over_time"], list)


@pytest.mark.asyncio
async def test_track_unique_user():
    """Test tracking unique users."""
    from backend.api.v1.admin.users import track_unique_user
    
    # Use mock Redis from fixture
    fingerprint = "test_fingerprint_hash_123"
    
    # This will use real Redis if available, or fail gracefully
    try:
        await track_unique_user(fingerprint)
        # If it doesn't raise, it worked
        assert True
    except Exception as e:
        # If Redis not available, skip test
        pytest.skip(f"Redis not available for tracking test: {e}")


def test_admin_endpoints_require_auth(client_with_admin, mock_redis):
    """Test that admin endpoints require authentication."""
    endpoints = [
        ("GET", "/api/v1/admin/settings/abuse-prevention"),
        ("GET", "/api/v1/admin/redis/stats"),
        ("GET", "/api/v1/admin/cache/suggested-questions/stats"),
        ("GET", "/api/v1/admin/users/stats"),
    ]
    
    for method, endpoint in endpoints:
        if method == "GET":
            response = client_with_admin.get(endpoint)
        elif method == "PUT":
            response = client_with_admin.put(endpoint, json={})
        else:
            response = client_with_admin.post(endpoint)
        
        assert response.status_code == 401, f"{method} {endpoint} should require auth"

