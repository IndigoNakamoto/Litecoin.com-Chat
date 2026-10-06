"""
Admin API endpoints for authentication.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import logging

from backend.rate_limiter import RateLimitConfig, check_rate_limit
from backend.utils.admin_auth import admin_operator, verify_admin_token  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiting configuration for admin auth endpoints
ADMIN_AUTH_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=10,
    requests_per_hour=100,
    identifier="admin_auth",
    enable_progressive_limits=True,
)


@router.post("/login")
async def admin_login(request: Request) -> Dict[str, Any]:
    """
    Verify admin token and return session info.
    
    Requires Bearer token authentication via Authorization header.
    Example: Authorization: Bearer <token>   (an ADMIN_TOKENS entry or the legacy ADMIN_TOKEN)
    
    Returns:
        Dictionary with authentication status, the operator name behind the token, and session info.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_AUTH_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    operator = admin_operator(auth_header)
    if operator is None:
        logger.warning(
            f"Unauthorized admin login attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    logger.info("Admin login operator=%s", operator)
    return {
        "authenticated": True,
        "operator": operator,
        "message": "Authentication successful"
    }


@router.get("/verify")
async def verify_admin(request: Request) -> Dict[str, Any]:
    """
    Verify current admin session/token.
    
    Requires Bearer token authentication via Authorization header.
    Example: Authorization: Bearer <ADMIN_TOKEN>
    
    Returns:
        Dictionary with authentication status.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_AUTH_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    operator = admin_operator(auth_header)
    if operator is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    return {
        "authenticated": True,
        "operator": operator,
        "message": "Token is valid"
    }

