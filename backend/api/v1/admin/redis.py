"""
Admin API endpoints for Redis management (bans and throttles).
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import logging

from backend.redis_client import get_redis_client
from backend.utils.admin_auth import operator_from_request, verify_admin_token
from backend.rate_limiter import RateLimitConfig, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiting configuration for admin redis endpoints
ADMIN_REDIS_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=20,
    requests_per_hour=200,
    identifier="admin_redis",
    enable_progressive_limits=True,
)


async def count_redis_keys(pattern: str) -> int:
    """
    Count Redis keys matching a pattern.
    
    Args:
        pattern: Redis key pattern (e.g., "rl:ban:*")
        
    Returns:
        Number of keys matching the pattern
    """
    redis = await get_redis_client()
    count = 0
    cursor = 0
    
    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        count += len(keys)
        if cursor == 0:
            break
    
    return count


async def delete_redis_keys(pattern: str) -> int:
    """
    Delete all Redis keys matching a pattern.
    
    Args:
        pattern: Redis key pattern (e.g., "rl:ban:*")
        
    Returns:
        Number of keys deleted
    """
    redis = await get_redis_client()
    deleted_count = 0
    cursor = 0
    
    while True:
        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
        if keys:
            # Delete keys in batches
            for key in keys:
                await redis.delete(key)
                deleted_count += 1
        if cursor == 0:
            break
    
    return deleted_count


@router.get("/stats")
async def get_redis_stats(request: Request) -> Dict[str, Any]:
    """
    Get statistics about bans and throttles in Redis.
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with counts of active bans and throttles.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_REDIS_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized Redis stats access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        # Count ban keys
        ban_patterns = [
            "rl:ban:*",
            "challenge:ban:*",
            "rl:violations:*",
            "challenge:violations:*"
        ]
        
        total_bans = 0
        for pattern in ban_patterns:
            count = await count_redis_keys(pattern)
            total_bans += count
        
        # Count throttle keys
        throttle_patterns = [
            "llm:throttle:*"
        ]
        
        total_throttles = 0
        for pattern in throttle_patterns:
            count = await count_redis_keys(pattern)
            total_throttles += count
        
        return {
            "bans": {
                "total": total_bans,
                "patterns": ban_patterns
            },
            "throttles": {
                "total": total_throttles,
                "patterns": throttle_patterns
            }
        }
    except Exception as e:
        logger.error(f"Error getting Redis stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve Redis stats"}
        )


@router.post("/clear-bans")
async def clear_bans(request: Request) -> Dict[str, Any]:
    """
    Clear all ban keys from Redis.
    
    This deletes:
    - rl:ban:* (rate limit bans)
    - challenge:ban:* (challenge bans)
    - rl:violations:* (rate limit violations)
    - challenge:violations:* (challenge violations)
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with number of keys deleted.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_REDIS_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized ban clear attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        ban_patterns = [
            "rl:ban:*",
            "challenge:ban:*",
            "rl:violations:*",
            "challenge:violations:*"
        ]
        
        total_deleted = 0
        for pattern in ban_patterns:
            deleted = await delete_redis_keys(pattern)
            total_deleted += deleted
        
        logger.info(f"Admin cleared {total_deleted} ban keys from Redis operator={operator_from_request(request)}")
        
        return {
            "success": True,
            "deleted_count": total_deleted,
            "message": f"Cleared {total_deleted} ban keys"
        }
    except Exception as e:
        logger.error(f"Error clearing bans: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to clear bans"}
        )


@router.post("/clear-throttles")
async def clear_throttles(request: Request) -> Dict[str, Any]:
    """
    Clear all throttle keys from Redis.
    
    This deletes:
    - llm:throttle:* (cost-based throttles)
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with number of keys deleted.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_REDIS_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized throttle clear attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        throttle_patterns = [
            "llm:throttle:*"
        ]
        
        total_deleted = 0
        for pattern in throttle_patterns:
            deleted = await delete_redis_keys(pattern)
            total_deleted += deleted
        
        logger.info(f"Admin cleared {total_deleted} throttle keys from Redis operator={operator_from_request(request)}")
        
        return {
            "success": True,
            "deleted_count": total_deleted,
            "message": f"Cleared {total_deleted} throttle keys"
        }
    except Exception as e:
        logger.error(f"Error clearing throttles: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to clear throttles"}
        )

