"""
Admin API endpoints for abuse prevention settings management.
Settings are stored in Redis with environment variable fallback.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import logging
import os
import json

from backend.redis_client import get_redis_client
from backend.utils.admin_auth import operator_from_request, verify_admin_token
from backend.rate_limiter import RateLimitConfig, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiting configuration for admin settings endpoints
ADMIN_SETTINGS_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=20,
    requests_per_hour=200,
    identifier="admin_settings",
    enable_progressive_limits=True,
)

# Redis key for storing settings
SETTINGS_REDIS_KEY = "admin:settings:abuse_prevention"


class AbusePreventionSettings(BaseModel):
    """Abuse prevention settings model."""
    global_rate_limit_per_minute: Optional[int] = Field(None, ge=1, description="Global rate limit per minute")
    global_rate_limit_per_hour: Optional[int] = Field(None, ge=1, description="Global rate limit per hour")
    enable_global_rate_limit: Optional[bool] = Field(None, description="Enable global rate limiting")
    challenge_ttl_seconds: Optional[int] = Field(None, ge=60, description="Challenge TTL in seconds")
    max_active_challenges_per_identifier: Optional[int] = Field(None, ge=1, description="Max active challenges per identifier")
    enable_challenge_response: Optional[bool] = Field(None, description="Enable challenge-response fingerprinting")
    high_cost_threshold_usd: Optional[float] = Field(None, ge=0.0001, description="High cost threshold in USD (10-minute window)")
    high_cost_window_seconds: Optional[int] = Field(None, ge=60, description="High cost window in seconds")
    enable_cost_throttling: Optional[bool] = Field(None, description="Enable cost-based throttling")
    cost_throttle_duration_seconds: Optional[int] = Field(None, ge=1, description="Cost throttle duration in seconds")
    daily_cost_limit_usd: Optional[float] = Field(None, ge=0.0001, description="Daily cost limit per identifier in USD")
    challenge_request_rate_limit_seconds: Optional[int] = Field(None, ge=1, description="Challenge request rate limit in seconds")
    daily_spend_limit_usd: Optional[float] = Field(None, ge=0.0001, description="Global daily LLM spend limit in USD")
    hourly_spend_limit_usd: Optional[float] = Field(None, ge=0.0001, description="Global hourly LLM spend limit in USD")
    enable_rate_limit_discord_alerts: Optional[bool] = Field(None, description="Enable Discord alerts when users hit rate limits")
    enable_spend_limit_discord_alerts: Optional[bool] = Field(None, description="Enable Discord alerts for global spend limit blocks")
    enable_cost_throttle_discord_alerts: Optional[bool] = Field(None, description="Enable Discord alerts for individual cost throttling")
    enable_ops_discord_alerts: Optional[bool] = Field(None, description="Enable Discord alerts for ops events (golden eval, stale docs, reconcile, health)")


async def get_setting_value(key: str, default: Any = None) -> Any:
    """Read one merged setting (Redis override, env fallback) without the HTTP layer."""
    try:
        current = await get_current_settings()
    except Exception:
        return default
    value = current.get(key)
    return default if value is None else value


async def get_settings_from_redis() -> Dict[str, Any]:
    """
    Get settings from Redis.
    
    Returns:
        Dictionary with settings, or empty dict if not found
    """
    try:
        redis = await get_redis_client()
        settings_json = await redis.get(SETTINGS_REDIS_KEY)
        if settings_json:
            return json.loads(settings_json)
    except Exception as e:
        logger.warning(f"Error reading settings from Redis: {e}")
    return {}


async def save_settings_to_redis(settings: Dict[str, Any]) -> None:
    """
    Save settings to Redis.
    
    Args:
        settings: Dictionary with settings to save
    """
    try:
        redis = await get_redis_client()
        # Store with no expiration (persistent until manually cleared or updated)
        await redis.set(SETTINGS_REDIS_KEY, json.dumps(settings))
        logger.info(f"Saved abuse prevention settings to Redis: {list(settings.keys())}")
    except Exception as e:
        logger.error(f"Error saving settings to Redis: {e}", exc_info=True)
        raise


def get_settings_from_env() -> Dict[str, Any]:
    """
    Get settings from environment variables (fallback).
    
    Returns:
        Dictionary with settings from environment
    """
    return {
        "global_rate_limit_per_minute": int(os.getenv("GLOBAL_RATE_LIMIT_PER_MINUTE", "1000")),
        "global_rate_limit_per_hour": int(os.getenv("GLOBAL_RATE_LIMIT_PER_HOUR", "50000")),
        "enable_global_rate_limit": os.getenv("ENABLE_GLOBAL_RATE_LIMIT", "true").lower() == "true",
        "challenge_ttl_seconds": int(os.getenv("CHALLENGE_TTL_SECONDS", "300")),
        "max_active_challenges_per_identifier": int(os.getenv("MAX_ACTIVE_CHALLENGES_PER_IDENTIFIER", "15")),
        "enable_challenge_response": os.getenv("ENABLE_CHALLENGE_RESPONSE", "true").lower() == "true",
        "high_cost_threshold_usd": float(os.getenv("HIGH_COST_THRESHOLD_USD", "0.001")),
        "high_cost_window_seconds": int(os.getenv("HIGH_COST_WINDOW_SECONDS", "600")),
        "enable_cost_throttling": os.getenv("ENABLE_COST_THROTTLING", "true").lower() == "true",
        "cost_throttle_duration_seconds": int(os.getenv("COST_THROTTLE_DURATION_SECONDS", "30")),
        "daily_cost_limit_usd": float(os.getenv("DAILY_COST_LIMIT_USD", "0.25")),
        "challenge_request_rate_limit_seconds": int(os.getenv("CHALLENGE_REQUEST_RATE_LIMIT_SECONDS", "1")),
        "daily_spend_limit_usd": float(os.getenv("DAILY_SPEND_LIMIT_USD", "5.00")),
        "hourly_spend_limit_usd": float(os.getenv("HOURLY_SPEND_LIMIT_USD", "1.00")),
        "enable_rate_limit_discord_alerts": os.getenv("ENABLE_RATE_LIMIT_DISCORD_ALERTS", "false").lower() == "true",
        "enable_spend_limit_discord_alerts": os.getenv("ENABLE_SPEND_LIMIT_DISCORD_ALERTS", "false").lower() == "true",
        "enable_cost_throttle_discord_alerts": os.getenv("ENABLE_COST_THROTTLE_DISCORD_ALERTS", "false").lower() == "true",
        "enable_ops_discord_alerts": os.getenv("DISCORD_OPS_ALERTS_ENABLED", "true").lower() == "true",
    }


async def get_current_settings() -> Dict[str, Any]:
    """
    Get current settings (Redis first, then env fallback).
    
    Returns:
        Dictionary with current settings
    """
    # Try Redis first
    redis_settings = await get_settings_from_redis()
    
    # Get env settings as base
    env_settings = get_settings_from_env()
    
    # Merge: Redis settings override env settings
    current_settings = {**env_settings, **redis_settings}
    
    # Ensure challenge_request_rate_limit_seconds defaults to 1 if not set
    if current_settings.get("challenge_request_rate_limit_seconds") is None:
        current_settings["challenge_request_rate_limit_seconds"] = 1
    
    return current_settings


@router.get("/abuse-prevention")
async def get_abuse_prevention_settings(request: Request) -> Dict[str, Any]:
    """
    Get current abuse prevention settings.
    
    Settings are read from Redis first, then fall back to environment variables.
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with current settings and their sources.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_SETTINGS_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized settings access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        current_settings = await get_current_settings()
        redis_settings = await get_settings_from_redis()
        
        # Determine which settings come from Redis vs env
        source_info = {}
        for key in current_settings.keys():
            if key in redis_settings:
                source_info[key] = "redis"
            else:
                source_info[key] = "environment"
        
        return {
            "settings": current_settings,
            "sources": source_info
        }
    except Exception as e:
        logger.error(f"Error getting settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve settings"}
        )


@router.put("/abuse-prevention")
async def update_abuse_prevention_settings(
    request: Request,
    settings: AbusePreventionSettings
) -> Dict[str, Any]:
    """
    Update abuse prevention settings.
    
    Settings are stored in Redis and will override environment variables.
    Only provided settings are updated (partial updates supported).
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with updated settings.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_SETTINGS_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized settings update attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        # Get current Redis settings
        current_redis_settings = await get_settings_from_redis()
        
        # Convert Pydantic model to dict, excluding None values
        update_dict = settings.model_dump(exclude_none=True)
        
        # Convert snake_case to match our keys
        # (Pydantic model uses snake_case, which matches our keys)
        
        # Merge with existing Redis settings
        updated_settings = {**current_redis_settings, **update_dict}
        
        # Save to Redis
        await save_settings_to_redis(updated_settings)
        
        # Clear the settings cache so new values are read immediately
        from backend.utils.settings_reader import clear_settings_cache
        clear_settings_cache()
        
        logger.info(f"Admin updated abuse prevention settings: {list(update_dict.keys())} operator={operator_from_request(request)}")
        
        return {
            "success": True,
            "message": "Settings updated successfully",
            "updated_settings": update_dict,
            "all_settings": updated_settings
        }
    except Exception as e:
        logger.error(f"Error updating settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to update settings"}
        )

