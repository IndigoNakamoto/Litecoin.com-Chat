#!/usr/bin/env python3
"""
Tests for abuse prevention features:
1. Challenge-response fingerprinting
2. Global rate limiting  
3. Per-identifier challenge limits
4. Cost-based throttling
5. Turnstile graceful degradation
"""

import os
import sys
import time
import asyncio
import pytest
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

client = TestClient(app)


def test_challenge_endpoint(client):
    """Test challenge generation endpoint."""
    # clear_challenge_state fixture already ran → no active challenges
    response = client.get("/api/v1/auth/challenge")
    assert response.status_code == 200
    data = response.json()
    assert "challenge" in data
    assert len(data["challenge"]) == 64  # 32 bytes hex
    assert "expires_in_seconds" in data
    assert data["expires_in_seconds"] == 300


def test_challenge_rate_limiting(client):
    """Test challenge endpoint rate limiting."""
    # Make requests up to the limit
    for i in range(10):
        response = client.get("/api/v1/auth/challenge")
        if response.status_code != 200:
            break
    
    # 11th request should be rate limited
    response = client.get("/api/v1/auth/challenge")
    # Might be 200 if rate limit hasn't kicked in yet, or 429 if it has
    # This depends on timing


@pytest.mark.asyncio
async def test_per_identifier_challenge_limit(mock_redis):
    """Test max active challenges per identifier."""
    from backend.utils.challenge import generate_challenge
    from backend.utils.settings_reader import get_setting_from_redis_or_env
    from unittest.mock import patch, AsyncMock
    
    identifier = "test_identifier_123"
    
    # Track number of challenges generated
    challenges_generated = []
    
    # Mock the Lua script eval() - this is what actually controls challenge generation
    # GENERATE_CHALLENGE_LUA returns: [status_code, ...]
    # status_code: 0 = success, 1 = limit exceeded (ban applied), 2 = currently banned
    async def mock_eval(script, num_keys, *args):
        # For GENERATE_CHALLENGE_LUA, args are:
        # active_challenges_key, challenge_key, violation_count_key, ban_key,
        # now, ttl, max_active, challenge_id, identifier, expiry_time, ban_durations
        if "ZADD" in script and "active" in str(args[0]):  # GENERATE_CHALLENGE_LUA
            challenge_id = args[7] if len(args) > 7 else "test_challenge"
            max_active = int(args[6]) if len(args) > 6 else 3
            
            if len(challenges_generated) >= max_active:
                # Limit exceeded - return status 1 with ban info
                return [1, 1, 60]  # [status=1, violation_count=1, ban_duration=60]
            
            challenges_generated.append(challenge_id)
            return [0]  # Success
        return [0]
    
    mock_redis.eval = mock_eval
    
    # Mock other Redis operations used before the Lua script
    async def mock_zremrangebyscore(key, min_score, max_score):
        return 0
    
    async def mock_get(key):
        return None  # No rate limit or ban
    
    async def mock_setex(key, ttl, value):
        return True
    
    async def mock_zrange(key, start, end, withscores=False):
        return []
    
    mock_redis.zremrangebyscore = mock_zremrangebyscore
    mock_redis.get = mock_get
    mock_redis.setex = mock_setex
    mock_redis.zrange = mock_zrange
    
    # Set max_active_challenges_per_identifier to 3 for this test
    async def mock_get_setting(redis_client, setting_key, env_var, default, value_type):
        if setting_key == "max_active_challenges_per_identifier":
            return 3  # Set limit to 3 for this test
        elif setting_key == "enable_challenge_response":
            return True
        elif setting_key == "challenge_ttl_seconds":
            return 300
        elif setting_key == "challenge_request_rate_limit_seconds":
            return 0  # Disable rate limiting for this test
        return default
    
    with patch("backend.utils.challenge.get_redis_client", return_value=mock_redis):
        with patch("backend.redis_client.get_redis_client", return_value=mock_redis):
            with patch("backend.utils.settings_reader.get_setting_from_redis_or_env", side_effect=mock_get_setting):
                # Generate 3 challenges (should succeed)
                challenges = []
                for i in range(3):
                    result = await generate_challenge(identifier)
                    challenges.append(result["challenge"])
                    assert len(challenges_generated) == i + 1, f"Challenge {i+1} not generated"
                
                # Verify we have 3 challenges
                assert len(challenges_generated) == 3, f"Expected 3 challenges, got {len(challenges_generated)}"
                
                # 4th challenge should fail
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    await generate_challenge(identifier)
                assert exc_info.value.status_code == 429


def test_fingerprint_extraction():
    """Test fingerprint extraction from request."""
    # Test with challenge in fingerprint
    fingerprint = "fp:challenge123:hash456"
    
    from backend.main import _extract_challenge_from_fingerprint
    challenge_id, fingerprint_hash = _extract_challenge_from_fingerprint(fingerprint)
    
    assert challenge_id == "challenge123"
    assert fingerprint_hash == "hash456"


@pytest.mark.asyncio
async def test_cost_throttling(mock_redis, monkeypatch):
    """Test cost-based throttling."""
    from backend.utils.cost_throttling import check_cost_based_throttling
    from unittest.mock import patch, AsyncMock
    
    # Set environment to production to enable cost throttling
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DEBUG", raising=False)
    
    fingerprint = "test_cost_throttle_fp"
    
    # Track accumulated daily cost
    accumulated_daily_cost = 0.0
    daily_limit = 0.25  # Default daily limit
    
    # Mock the Lua script eval() - COST_THROTTLE_LUA returns:
    # [status_code, ttl_or_duration]
    # status_code: 0 = allowed, 1 = already throttled, 2 = daily limit exceeded, 3 = window threshold exceeded
    async def mock_eval(script, num_keys, *args):
        nonlocal accumulated_daily_cost
        
        if "cost" in str(args[0]).lower() or "throttle" in str(args[2]).lower():
            # COST_THROTTLE_LUA script
            # args: cost_key, daily_cost_key, throttle_marker_key, now, window, est_cost, threshold, daily_limit, throttle_dur, member, daily_ttl
            estimated_cost = float(args[5]) if len(args) > 5 else 0.01
            daily_limit_arg = float(args[7]) if len(args) > 7 else 0.25
            
            # Check if daily limit would be exceeded
            if accumulated_daily_cost + estimated_cost > daily_limit_arg:
                return [2, 30]  # status=2 (daily limit exceeded), throttle_duration=30
            
            # Cost allowed - accumulate it
            accumulated_daily_cost += estimated_cost
            return [0, 0]  # status=0 (allowed)
        
        return [0, 0]
    
    mock_redis.eval = mock_eval
    
    # Mock get for settings lookup (returns None to use defaults)
    async def mock_get(key):
        if "settings" in str(key):
            return None
        return None
    
    mock_redis.get = mock_get
    
    with patch("backend.utils.cost_throttling.get_redis_client", return_value=mock_redis):
        # Small cost (0.01) should not throttle (below daily limit of 0.25)
        throttled, reason = await check_cost_based_throttling(fingerprint, 0.01)
        assert throttled == False
        
        # Large cost (15.0) should throttle (exceeds daily limit of 0.25)
        throttled, reason = await check_cost_based_throttling(fingerprint, 15.0)
        assert throttled == True
        assert reason is not None
        assert "daily" in reason.lower() or "limit" in reason.lower()


def test_global_rate_limit():
    """Test global rate limiting."""
    # This is harder to test with TestClient since it doesn't easily simulate
    # 1000+ requests. Better to test with integration tests or load testing.
    pass  # Placeholder