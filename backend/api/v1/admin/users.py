"""
Admin API endpoints for user statistics tracking by fingerprint.
Tracks unique users over time with daily aggregation.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, List
import logging
from datetime import datetime, timedelta

from backend.redis_client import get_redis_client
from backend.utils.admin_auth import operator_from_request, verify_admin_token
from backend.rate_limiter import RateLimitConfig, check_rate_limit
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiting configuration for admin user endpoints
ADMIN_USERS_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=30,
    requests_per_hour=200,
    identifier="admin_users",
    enable_progressive_limits=True,
)


async def track_unique_user(fingerprint_hash: str) -> None:
    """
    Track a unique user by fingerprint hash.
    
    This function:
    1. Adds fingerprint to global set of all-time unique users
    2. Adds fingerprint to today's set of unique users
    3. Sets expiry for today's set to clean up after retention period
    
    Args:
        fingerprint_hash: Stable fingerprint hash (without challenge prefix)
    """
    if not fingerprint_hash:
        return
    
    redis = await get_redis_client()
    now = datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    
    # Track in global set (all-time unique users)
    global_key = "users:unique:all_time"
    await redis.sadd(global_key, fingerprint_hash)
    # Keep global set indefinitely (no expiry)
    
    # Track in today's set (daily unique users)
    daily_key = f"users:unique:daily:{today_str}"
    await redis.sadd(daily_key, fingerprint_hash)
    # Expire daily sets after 90 days (retention period)
    await redis.expire(daily_key, 90 * 24 * 60 * 60)
    
    logger.debug(f"Tracked unique user: {fingerprint_hash[:16]}... for date {today_str}")


async def get_all_time_unique_users() -> int:
    """
    Get total number of unique users (all-time).
    
    Returns:
        Total count of unique fingerprints
    """
    redis = await get_redis_client()
    global_key = "users:unique:all_time"
    count = await redis.scard(global_key)
    return count


async def get_daily_unique_users(date_str: str) -> int:
    """
    Get number of unique users for a specific date.
    
    Args:
        date_str: Date string in format "YYYY-MM-DD"
        
    Returns:
        Count of unique users for that date
    """
    redis = await get_redis_client()
    daily_key = f"users:unique:daily:{date_str}"
    count = await redis.scard(daily_key)
    return count


async def get_users_over_time(days: int = 30) -> List[Dict[str, Any]]:
    """
    Get unique user counts over the last N days.
    
    Args:
        days: Number of days to retrieve (default: 30)
        
    Returns:
        List of dictionaries with date and unique user count
    """
    redis = await get_redis_client()
    now = datetime.utcnow()
    results = []
    
    for i in range(days):
        date = now - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        daily_key = f"users:unique:daily:{date_str}"
        count = await redis.scard(daily_key)
        results.append({
            "date": date_str,
            "unique_users": count
        })
    
    # Return in chronological order (oldest first)
    return list(reversed(results))


async def get_average_users_per_day(days: int = 30) -> float:
    """
    Calculate average unique users per day over the last N days.
    
    Args:
        days: Number of days to average (default: 30)
        
    Returns:
        Average unique users per day (rounded to 2 decimal places)
    """
    users_over_time = await get_users_over_time(days)
    if not users_over_time:
        return 0.0
    
    total_users = sum(day["unique_users"] for day in users_over_time)
    average = total_users / len(users_over_time)
    return round(average, 2)


@router.get("/stats")
async def get_user_stats(request: Request, days: int = 30) -> Dict[str, Any]:
    """
    Get comprehensive user statistics.
    
    Requires Bearer token authentication via Authorization header.
    
    Query Parameters:
        days: Number of days to include in historical data (default: 30, max: 365)
    
    Returns:
        Dictionary with:
        - total_unique_users: All-time unique user count
        - users_over_time: Array of {date, unique_users} for last N days
        - average_users_per_day: Average unique users per day
        - today_unique_users: Today's unique user count
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_USERS_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized user stats access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    # Limit days to reasonable range
    days = max(1, min(days, 365))
    
    try:
        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")
        
        # Get all statistics in parallel
        total_unique, today_unique, users_over_time, avg_per_day = await asyncio.gather(
            get_all_time_unique_users(),
            get_daily_unique_users(today_str),
            get_users_over_time(days),
            get_average_users_per_day(days)
        )
        
        return {
            "total_unique_users": total_unique,
            "today_unique_users": today_unique,
            "average_users_per_day": avg_per_day,
            "users_over_time": users_over_time,
            "days_tracked": days
        }
    except Exception as e:
        logger.error(f"Error getting user statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve user statistics"}
        )

