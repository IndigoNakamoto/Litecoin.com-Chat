"""
Admin API endpoint for LLM usage statistics.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import logging

from backend.monitoring.spend_limit import get_current_usage
from backend.utils.admin_auth import operator_from_request, verify_admin_token
from backend.rate_limiter import RateLimitConfig, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiting configuration for admin usage endpoints
ADMIN_USAGE_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=30,
    requests_per_hour=200,
    identifier="admin_usage",
    enable_progressive_limits=True,
)


@router.get("/usage")
async def get_usage(request: Request) -> Dict[str, Any]:
    """
    Get current daily and hourly LLM usage statistics.
    
    Requires Bearer token authentication via Authorization header.
    Example: Authorization: Bearer <ADMIN_TOKEN>
    
    Returns:
        Dictionary with daily and hourly usage information including costs, limits, percentages, and tokens.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_USAGE_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized usage statistics access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        usage_info = await get_current_usage()
        return usage_info
    except Exception as e:
        logger.error(f"Error getting usage statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve usage statistics"}
        )


@router.get("/usage/status")
async def get_usage_status(request: Request) -> Dict[str, Any]:
    """
    Get simplified usage status for frontend warnings.
    Returns warning level if approaching limits.
    
    This endpoint is PUBLIC (no authentication required) to allow the frontend
    to display usage warnings to users. It only returns status and warning
    levels, not sensitive cost information or percentages.
    
    Returns:
        Dictionary with status and warning level only (no cost data or percentages).
    """
    # Rate limiting (more lenient for public endpoint)
    await check_rate_limit(request, ADMIN_USAGE_RATE_LIMIT)
    
    try:
        usage_info = await get_current_usage()
        
        daily_percentage = usage_info["daily"]["percentage_used"]
        hourly_percentage = usage_info["hourly"]["percentage_used"]
        
        # Determine warning level
        warning_level = None
        if daily_percentage >= 100 or hourly_percentage >= 100:
            warning_level = "error"
        elif daily_percentage >= 80 or hourly_percentage >= 80:
            warning_level = "warning"
        elif daily_percentage >= 60 or hourly_percentage >= 60:
            warning_level = "info"
        
        # Return only status and warning level (no percentages or cost information)
        return {
            "status": "ok" if warning_level is None else warning_level,
            "warning_level": warning_level,
            # Note: Removed daily_percentage, hourly_percentage, and remaining amounts for security
        }
    except Exception as e:
        logger.error(f"Error getting usage status: {e}", exc_info=True)
        # Return safe defaults on error
        return {
            "status": "ok",
            "warning_level": None,
        }

