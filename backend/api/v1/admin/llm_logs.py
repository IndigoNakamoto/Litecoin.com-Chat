"""
Admin API endpoint for querying LLM request logs from MongoDB.
Provides aggregated statistics for Grafana visualization.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from backend.dependencies import get_llm_request_logs_collection
from backend.utils.admin_auth import operator_from_request, verify_admin_token
from backend.rate_limiter import RateLimitConfig, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiting configuration for admin log endpoints
ADMIN_LOGS_RATE_LIMIT = RateLimitConfig(
    requests_per_minute=60,
    requests_per_hour=500,
    identifier="admin_logs",
    enable_progressive_limits=False,
)


@router.get("/llm-logs/stats")
async def get_llm_logs_stats(
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Number of hours to look back"),
) -> Dict[str, Any]:
    """
    Get aggregated statistics from LLM request logs.
    
    This endpoint is designed for Grafana JSON API data source.
    Returns time-series data aggregated by hour.
    
    Requires Bearer token authentication via Authorization header.
    Example: Authorization: Bearer <ADMIN_TOKEN>
    
    Args:
        hours: Number of hours to look back (1-168, default: 24)
    
    Returns:
        Dictionary with aggregated statistics including:
        - hourly_aggregates: List of hourly stats with timestamp, requests, tokens, costs
        - totals: Overall totals for the time period
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_LOGS_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized LLM logs access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        collection = await get_llm_request_logs_collection()
        
        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # Aggregate by hour
        # Using $dateToString for compatibility across MongoDB versions
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": start_time,
                        "$lte": end_time
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$timestamp"},
                        "month": {"$month": "$timestamp"},
                        "day": {"$dayOfMonth": "$timestamp"},
                        "hour": {"$hour": "$timestamp"}
                    },
                    "requests": {"$sum": 1},
                    "success_requests": {
                        "$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}
                    },
                    "error_requests": {
                        "$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}
                    },
                    "total_input_tokens": {"$sum": "$input_tokens"},
                    "total_output_tokens": {"$sum": "$output_tokens"},
                    "total_cost_usd": {"$sum": "$cost_usd"},
                    "avg_duration_seconds": {"$avg": "$duration_seconds"},
                    "cache_hits": {
                        "$sum": {"$cond": [{"$eq": ["$cache_hit", True]}, 1, 0]}
                    }
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        
        hourly_aggregates = []
        async for doc in collection.aggregate(pipeline):
            # Reconstruct datetime from grouped fields
            hour_id = doc["_id"]
            hour_dt = datetime(
                hour_id["year"],
                hour_id["month"],
                hour_id["day"],
                hour_id["hour"],
                0, 0, 0
            )
            
            hourly_aggregates.append({
                "timestamp": hour_dt.isoformat() + "Z",
                "requests": doc["requests"],
                "success_requests": doc["success_requests"],
                "error_requests": doc["error_requests"],
                "input_tokens": doc["total_input_tokens"],
                "output_tokens": doc["total_output_tokens"],
                "total_tokens": doc["total_input_tokens"] + doc["total_output_tokens"],
                "cost_usd": round(doc["total_cost_usd"], 6),
                "avg_duration_seconds": round(doc["avg_duration_seconds"], 3),
                "cache_hits": doc["cache_hits"],
                "cache_hit_rate": round(doc["cache_hits"] / doc["requests"] * 100, 2) if doc["requests"] > 0 else 0
            })
        
        # Get overall totals
        totals_pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": start_time,
                        "$lte": end_time
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_requests": {"$sum": 1},
                    "total_success": {
                        "$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}
                    },
                    "total_errors": {
                        "$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}
                    },
                    "total_input_tokens": {"$sum": "$input_tokens"},
                    "total_output_tokens": {"$sum": "$output_tokens"},
                    "total_cost_usd": {"$sum": "$cost_usd"},
                    "avg_duration_seconds": {"$avg": "$duration_seconds"},
                    "total_cache_hits": {
                        "$sum": {"$cond": [{"$eq": ["$cache_hit", True]}, 1, 0]}
                    }
                }
            }
        ]
        
        totals_result = await collection.aggregate(totals_pipeline).to_list(length=1)
        totals = totals_result[0] if totals_result else {
            "total_requests": 0,
            "total_success": 0,
            "total_errors": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "avg_duration_seconds": 0.0,
            "total_cache_hits": 0
        }
        
        return {
            "hourly_aggregates": hourly_aggregates,
            "totals": {
                "total_requests": totals["total_requests"],
                "total_success": totals["total_success"],
                "total_errors": totals["total_errors"],
                "total_input_tokens": totals["total_input_tokens"],
                "total_output_tokens": totals["total_output_tokens"],
                "total_tokens": totals["total_input_tokens"] + totals["total_output_tokens"],
                "total_cost_usd": round(totals["total_cost_usd"], 6),
                "avg_duration_seconds": round(totals["avg_duration_seconds"], 3),
                "total_cache_hits": totals["total_cache_hits"],
                "cache_hit_rate": round(totals["total_cache_hits"] / totals["total_requests"] * 100, 2) if totals["total_requests"] > 0 else 0
            },
            "time_range": {
                "start": start_time.isoformat() + "Z",
                "end": end_time.isoformat() + "Z",
                "hours": hours
            }
        }
    except Exception as e:
        logger.error(f"Error getting LLM logs statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve LLM logs statistics"}
        )


@router.get("/llm-logs/recent")
async def get_recent_llm_logs(
    request: Request,
    limit: int = Query(100, ge=1, le=1000, description="Number of recent logs to return"),
) -> Dict[str, Any]:
    """
    Get recent LLM request logs.
    
    Requires Bearer token authentication via Authorization header.
    
    Args:
        limit: Maximum number of logs to return (1-1000, default: 100)
    
    Returns:
        Dictionary with list of recent log entries
    """
    # Rate limiting
    await check_rate_limit(request, ADMIN_LOGS_RATE_LIMIT)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    # Verify authentication
    if not verify_admin_token(auth_header):
        logger.warning(
            f"Unauthorized LLM logs access attempt from IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Invalid or missing admin token"}
        )
    
    try:
        collection = await get_llm_request_logs_collection()
        
        # Get recent logs, sorted by timestamp descending
        cursor = collection.find().sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            # Convert ObjectId to string and format timestamp
            log_entry = {
                "id": str(doc["_id"]),
                "request_id": doc.get("request_id", ""),
                "timestamp": doc["timestamp"].isoformat() + "Z",
                "user_question": doc.get("user_question", "")[:100],  # Truncate for display
                "assistant_response_length": doc.get("response_length", 0),
                "input_tokens": doc.get("input_tokens", 0),
                "output_tokens": doc.get("output_tokens", 0),
                "cost_usd": round(doc.get("cost_usd", 0.0), 6),
                "model": doc.get("model", ""),
                "duration_seconds": round(doc.get("duration_seconds", 0.0), 3),
                "status": doc.get("status", "unknown"),
                "sources_count": doc.get("sources_count", 0),
                "cache_hit": doc.get("cache_hit", False),
                "cache_type": doc.get("cache_type"),
                "endpoint_type": doc.get("endpoint_type", ""),
            }
            logs.append(log_entry)
        
        return {
            "logs": logs,
            "count": len(logs)
        }
    except Exception as e:
        logger.error(f"Error getting recent LLM logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "Failed to retrieve LLM logs"}
        )

