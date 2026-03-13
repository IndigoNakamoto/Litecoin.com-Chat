"""
Admin API endpoints for cache management.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import logging
import os
import hmac

from backend.cache_utils import suggested_question_cache, query_cache
from backend.rate_limiter import RateLimitConfig, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiting configuration for admin cache endpoints
ADMIN_CACHE_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=10,
    requests_per_hour=100,
    identifier="admin_cache",
    enable_progressive_limits=True,
)


def verify_admin_token(authorization: str = None) -> bool:
    """
    Verify admin token from Authorization header.
    
    Args:
        authorization: Authorization header value (e.g., "Bearer <token>")
        
    Returns:
        True if token is valid, False otherwise
    """
    if not authorization:
        return False
    
    # Extract token from "Bearer <token>" format
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            return False
    except ValueError:
        return False
    
    # Get expected token from environment
    expected_token = os.getenv("ADMIN_TOKEN")
    if not expected_token:
        logger.warning("ADMIN_TOKEN not set, admin endpoint authentication disabled")
        return False
    
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(token, expected_token)


@router.get("/suggested-questions/stats")
async def get_cache_stats(request: Request) -> Dict[str, Any]:
    """
    Get statistics about the suggested questions cache.
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with cache statistics.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_CACHE_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized cache stats access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        cache_size = await suggested_question_cache.get_cache_size()
        
        return {
            "cache_size": cache_size,
            "cache_type": "suggested_questions"
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve cache stats"}
        )


@router.post("/suggested-questions/clear")
async def clear_suggested_questions_cache(request: Request) -> Dict[str, Any]:
    """
    Clear the suggested questions cache.
    
    This deletes all keys matching the pattern: suggested_question:*
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with operation result.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_CACHE_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized cache clear attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        # Get cache size before clearing
        cache_size_before = await suggested_question_cache.get_cache_size()
        
        # Clear the cache
        await suggested_question_cache.clear()
        
        logger.info(f"Admin cleared suggested questions cache ({cache_size_before} entries)")
        
        return {
            "success": True,
            "cleared_count": cache_size_before,
            "message": f"Cleared {cache_size_before} entries from suggested questions cache"
        }
    except Exception as e:
        logger.error(f"Error clearing cache: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to clear cache"}
        )


@router.post("/suggested-questions/refresh")
async def refresh_suggested_questions_cache(request: Request) -> Dict[str, Any]:
    """
    Regenerate the suggested questions cache.
    
    This triggers a background refresh of the cache by pre-generating responses
    for all active suggested questions.
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with operation result.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_CACHE_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized cache refresh attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        # Import the refresh function from main.py
        from backend.main import refresh_suggested_question_cache
        
        # Trigger the refresh (this runs in the background)
        result = await refresh_suggested_question_cache()
        
        logger.info("Admin triggered suggested questions cache refresh")
        
        return {
            "success": True,
            "message": "Cache refresh initiated. This may take a few minutes to complete.",
            "status": "processing"
        }
    except Exception as e:
        logger.error(f"Error refreshing cache: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to refresh cache"}
        )


@router.get("/semantic/stats")
async def get_semantic_cache_stats(request: Request) -> Dict[str, Any]:
    """
    Get statistics about the semantic cache.
    
    Returns stats for both Redis Stack vector cache (if enabled) and
    legacy in-memory semantic cache (if enabled).
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with cache statistics.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_CACHE_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized semantic cache stats access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        import os
        USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "false").lower() == "true"
        
        result = {
            "redis_vector_cache": None,
            "legacy_semantic_cache": None,
            "active_cache": None
        }
        
        # Get Redis Stack vector cache stats (if enabled)
        if USE_REDIS_CACHE:
            try:
                from backend.rag_pipeline import _get_redis_vector_cache
                redis_cache = _get_redis_vector_cache()
                if redis_cache:
                    stats = await redis_cache.stats()
                    result["redis_vector_cache"] = stats
                    result["active_cache"] = "redis_vector_cache"
            except Exception as e:
                logger.warning(f"Error getting Redis vector cache stats: {e}")
        
        # Get legacy semantic cache stats (if enabled)
        try:
            from backend.api.v1.sync.payload import _global_rag_pipeline
            if _global_rag_pipeline and hasattr(_global_rag_pipeline, "semantic_cache") and _global_rag_pipeline.semantic_cache:
                stats = _global_rag_pipeline.semantic_cache.stats()
                result["legacy_semantic_cache"] = stats
                if not result["active_cache"]:
                    result["active_cache"] = "legacy_semantic_cache"
        except Exception as e:
            logger.warning(f"Error getting legacy semantic cache stats: {e}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting semantic cache stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve semantic cache stats"}
        )


@router.post("/semantic/clear")
async def clear_semantic_cache(request: Request) -> Dict[str, Any]:
    """
    Clear the semantic cache.
    
    This clears both Redis Stack vector cache (if enabled) and
    legacy in-memory semantic cache (if enabled).
    
    Requires Bearer token authentication via Authorization header.
    
    Returns:
        Dictionary with operation result.
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_CACHE_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized semantic cache clear attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        import os
        USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "false").lower() == "true"
        
        cleared_caches = []
        redis_cleared = False
        legacy_cleared = False
        redis_stats_before = None
        legacy_stats_before = None
        
        # Clear Redis Stack vector cache (if enabled)
        if USE_REDIS_CACHE:
            try:
                from backend.rag_pipeline import _get_redis_vector_cache
                redis_cache = _get_redis_vector_cache()
                if redis_cache:
                    redis_stats_before = await redis_cache.stats()
                    cleared = await redis_cache.clear()
                    if cleared:
                        redis_cleared = True
                        entries_cleared = redis_stats_before.get("entries", 0)
                        cleared_caches.append(f"Redis Stack vector cache ({entries_cleared} entries)")
                        logger.info(f"Admin cleared Redis Stack vector cache ({entries_cleared} entries)")
            except Exception as e:
                logger.warning(f"Error clearing Redis vector cache: {e}")
        
        # Clear legacy semantic cache (if enabled)
        try:
            from backend.api.v1.sync.payload import _global_rag_pipeline
            if _global_rag_pipeline and hasattr(_global_rag_pipeline, "semantic_cache") and _global_rag_pipeline.semantic_cache:
                legacy_stats_before = _global_rag_pipeline.semantic_cache.stats()
                _global_rag_pipeline.semantic_cache.clear()
                legacy_cleared = True
                entries_cleared = legacy_stats_before.get("size", 0)
                cleared_caches.append(f"Legacy semantic cache ({entries_cleared} entries)")
                logger.info(f"Admin cleared legacy semantic cache ({entries_cleared} entries)")
        except Exception as e:
            logger.warning(f"Error clearing legacy semantic cache: {e}")
        
        if not redis_cleared and not legacy_cleared:
            return {
                "success": True,
                "message": "No semantic cache was active to clear",
                "cleared_caches": []
            }
        
        message = f"Cleared semantic cache: {', '.join(cleared_caches)}"
        
        return {
            "success": True,
            "message": message,
            "cleared_caches": cleared_caches,
            "redis_vector_cache": {
                "cleared": redis_cleared,
                "entries_before": redis_stats_before.get("entries", 0) if redis_stats_before else 0
            } if USE_REDIS_CACHE else None,
            "legacy_semantic_cache": {
                "cleared": legacy_cleared,
                "entries_before": legacy_stats_before.get("size", 0) if legacy_stats_before else 0
            } if legacy_stats_before else None
        }
        
    except Exception as e:
        logger.error(f"Error clearing semantic cache: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to clear semantic cache"}
        )


@router.get("/response/stats")
async def get_response_cache_stats(request: Request) -> Dict[str, Any]:
    """
    Get statistics about all response caches (query cache + semantic cache).

    Requires Bearer token authentication via Authorization header.
    """
    await check_rate_limit(request, ADMIN_CACHE_RATE_LIMIT)

    auth_header = request.headers.get("Authorization")
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized response cache stats access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )

    try:
        USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "false").lower() == "true"

        result: Dict[str, Any] = {
            "query_cache": query_cache.stats(),
            "semantic_cache": None,
        }

        if USE_REDIS_CACHE:
            try:
                from backend.rag_pipeline import _get_redis_vector_cache
                redis_cache = _get_redis_vector_cache()
                if redis_cache:
                    result["semantic_cache"] = await redis_cache.stats()
            except Exception as e:
                logger.warning(f"Error getting Redis vector cache stats: {e}")
        else:
            try:
                from backend.api.v1.sync.payload import _global_rag_pipeline
                if _global_rag_pipeline and hasattr(_global_rag_pipeline, "semantic_cache") and _global_rag_pipeline.semantic_cache:
                    result["semantic_cache"] = _global_rag_pipeline.semantic_cache.stats()
            except Exception as e:
                logger.warning(f"Error getting legacy semantic cache stats: {e}")

        return result

    except Exception as e:
        logger.error(f"Error getting response cache stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve response cache stats"}
        )


@router.post("/response/clear")
async def clear_response_caches(request: Request) -> Dict[str, Any]:
    """
    Clear all response caches: the exact-match query cache and
    the semantic cache (Redis vector or legacy in-memory).

    Requires Bearer token authentication via Authorization header.
    """
    await check_rate_limit(request, ADMIN_CACHE_RATE_LIMIT)

    auth_header = request.headers.get("Authorization")
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized response cache clear attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )

    try:
        USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "false").lower() == "true"
        cleared = []

        # 1. Query cache (in-memory exact match)
        query_stats = query_cache.stats()
        query_size = query_stats.get("size", 0)
        query_cache.clear()
        cleared.append(f"Query cache ({query_size} entries)")
        logger.info(f"Admin cleared query cache ({query_size} entries)")

        # 2. Semantic cache (Redis or legacy)
        if USE_REDIS_CACHE:
            try:
                from backend.rag_pipeline import _get_redis_vector_cache
                redis_cache = _get_redis_vector_cache()
                if redis_cache:
                    stats_before = await redis_cache.stats()
                    await redis_cache.clear()
                    entries = stats_before.get("entries", 0)
                    cleared.append(f"Redis semantic cache ({entries} entries)")
                    logger.info(f"Admin cleared Redis semantic cache ({entries} entries)")
            except Exception as e:
                logger.warning(f"Error clearing Redis vector cache: {e}")
        else:
            try:
                from backend.api.v1.sync.payload import _global_rag_pipeline
                if _global_rag_pipeline and hasattr(_global_rag_pipeline, "semantic_cache") and _global_rag_pipeline.semantic_cache:
                    stats_before = _global_rag_pipeline.semantic_cache.stats()
                    _global_rag_pipeline.semantic_cache.clear()
                    entries = stats_before.get("size", 0)
                    cleared.append(f"Legacy semantic cache ({entries} entries)")
                    logger.info(f"Admin cleared legacy semantic cache ({entries} entries)")
            except Exception as e:
                logger.warning(f"Error clearing legacy semantic cache: {e}")

        return {
            "success": True,
            "message": f"Cleared {len(cleared)} response cache(s): {', '.join(cleared)}",
            "cleared_caches": cleared,
        }

    except Exception as e:
        logger.error(f"Error clearing response caches: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to clear response caches"}
        )

