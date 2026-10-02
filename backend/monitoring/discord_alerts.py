"""
Discord Alerting Module for LLM Spend Limit Monitoring

This module provides Discord webhook integration for sending alerts when
spend limits are approached or exceeded.
"""

import os
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# Discord webhook URL (optional)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


async def send_spend_limit_alert(
    limit_type: str,
    current_cost: float,
    limit: float,
    percentage: float,
    is_exceeded: bool
) -> bool:
    """
    Send a Discord alert for spend limit threshold crossing.
    
    Args:
        limit_type: "daily" or "hourly"
        current_cost: Current cost in USD
        limit: Limit in USD
        percentage: Percentage of limit used
        is_exceeded: True if limit is exceeded, False if at warning threshold (80%)
    
    Returns:
        True if alert was sent successfully, False otherwise
    """
    if not DISCORD_WEBHOOK_URL:
        # Discord webhook not configured, skip silently
        return False
    
    try:
        # Determine alert level and color
        if is_exceeded:
            title = f"🚨 LLM Spend Limit EXCEEDED - {limit_type.upper()}"
            description = f"The {limit_type} LLM spend limit has been **EXCEEDED**."
            color = 0xFF0000  # Red
            status_emoji = "🔴"
        else:
            title = f"⚠️ LLM Spend Limit WARNING - {limit_type.upper()}"
            description = f"The {limit_type} LLM spend limit has been approached (80% threshold)."
            color = 0xFFAA00  # Orange/Yellow
            status_emoji = "🟡"
        
        remaining = max(0.0, limit - current_cost)
        
        # Format Discord embed
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": [
                {
                    "name": "Current Usage",
                    "value": f"${current_cost:.4f} / ${limit:.2f} ({percentage:.1f}%)",
                    "inline": False
                },
                {
                    "name": "Limit Type",
                    "value": limit_type.upper(),
                    "inline": True
                },
                {
                    "name": "Current Cost",
                    "value": f"${current_cost:.4f}",
                    "inline": True
                },
                {
                    "name": "Limit",
                    "value": f"${limit:.2f}",
                    "inline": True
                },
                {
                    "name": "Percentage Used",
                    "value": f"{percentage:.1f}%",
                    "inline": True
                },
                {
                    "name": "Remaining",
                    "value": f"${remaining:.4f}",
                    "inline": True
                },
            ],
            "footer": {
                "text": "Litecoin Knowledge Hub - Cost Monitoring"
            },
            "timestamp": None  # Will be set by Discord
        }
        
        payload = {
            "embeds": [embed]
        }
        
        # Send webhook request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(DISCORD_WEBHOOK_URL, json=payload)
            response.raise_for_status()
        
        logger.info(f"Discord alert sent successfully: {limit_type} limit {'exceeded' if is_exceeded else 'warning'}")
        return True
        
    except httpx.HTTPError as e:
        logger.error(f"Failed to send Discord alert (HTTP error): {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Failed to send Discord alert: {e}", exc_info=True)
        return False


_LEVEL_COLORS = {
    "info": 0x3B82F6,     # blue
    "success": 0x22C55E,  # green
    "warning": 0xFFAA00,  # amber
    "error": 0xFF0000,    # red
}


async def send_ops_alert(
    title: str,
    description: str,
    level: str = "info",
    fields: Optional[list] = None,
    footer: str = "Litecoin Knowledge Hub - Operations",
) -> bool:
    """
    Generic Discord embed for operational events (health, golden-set eval,
    stale-doc report, reconciliation, incident pin). Honors the
    `enable_ops_discord_alerts` admin setting when Redis settings are reachable
    and falls back to DISCORD_OPS_ALERTS_ENABLED (default true).

    `fields` is a list of {"name", "value", "inline"} dicts (max 25).
    """
    webhook = os.getenv("DISCORD_OPS_WEBHOOK_URL") or DISCORD_WEBHOOK_URL or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook:
        return False

    enabled = os.getenv("DISCORD_OPS_ALERTS_ENABLED", "true").lower() == "true"
    try:
        from backend.api.v1.admin.settings import get_setting_value  # optional

        enabled = bool(await get_setting_value("enable_ops_discord_alerts", enabled))
    except Exception:
        pass
    if not enabled:
        return False

    embed = {
        "title": title[:256],
        "description": description[:4000],
        "color": _LEVEL_COLORS.get(level, _LEVEL_COLORS["info"]),
        "fields": [
            {"name": str(f.get("name", ""))[:256], "value": str(f.get("value", ""))[:1024], "inline": bool(f.get("inline", True))}
            for f in (fields or [])[:25]
        ],
        "footer": {"text": footer},
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook, json={"embeds": [embed]})
            response.raise_for_status()
        logger.info("Discord ops alert sent: %s", title)
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to send Discord ops alert: %s", e)
        return False


def _mask_identifier(identifier: str) -> str:
    """
    Mask an identifier (IP or fingerprint) for privacy in Discord alerts.
    
    Args:
        identifier: The full identifier string
        
    Returns:
        Masked identifier showing only first/last few characters
    """
    if not identifier:
        return "unknown"
    
    # For IPs, show first octet and mask rest
    if "." in identifier and identifier.count(".") == 3:
        # IPv4: show first octet
        parts = identifier.split(".")
        return f"{parts[0]}.***.***"
    elif ":" in identifier:
        # IPv6 or fingerprint with colons
        if identifier.startswith("fp:"):
            # Fingerprint: show type and last 4 chars
            return f"fp:***{identifier[-4:]}"
        else:
            # IPv6: show first segment
            parts = identifier.split(":")
            return f"{parts[0]}:***"
    else:
        # Other identifier: show first 4 and last 4 chars
        if len(identifier) > 10:
            return f"{identifier[:4]}***{identifier[-4:]}"
        return f"{identifier[:2]}***"


async def send_rate_limit_alert(
    limit_type: str,
    identifier: str,
    requests_made: int,
    limit: int,
    endpoint_type: str = "chat",
) -> bool:
    """
    Send a Discord alert when a user hits their rate limit.
    
    Args:
        limit_type: "minute" or "hour" indicating which limit was hit
        identifier: The user identifier (IP or fingerprint) - will be masked
        requests_made: Number of requests made in the window
        limit: The rate limit that was exceeded
        endpoint_type: The endpoint type (e.g., "chat", "chat_stream")
    
    Returns:
        True if alert was sent successfully, False otherwise
    """
    if not DISCORD_WEBHOOK_URL:
        # Discord webhook not configured, skip silently
        return False
    
    try:
        # Mask identifier for privacy
        masked_id = _mask_identifier(identifier)
        
        # Format limit type for display
        limit_display = "per minute" if limit_type == "minute" else "per hour"
        window_display = "Minute" if limit_type == "minute" else "Hourly"
        
        title = f"🚫 Rate Limit Hit - {window_display.upper()}"
        description = f"A user has exceeded their {limit_display} rate limit."
        color = 0xFF6B6B  # Coral red
        
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": [
                {
                    "name": "User Identifier",
                    "value": f"`{masked_id}`",
                    "inline": True
                },
                {
                    "name": "Endpoint",
                    "value": endpoint_type,
                    "inline": True
                },
                {
                    "name": "Limit Type",
                    "value": window_display,
                    "inline": True
                },
                {
                    "name": "Requests Made",
                    "value": str(requests_made),
                    "inline": True
                },
                {
                    "name": "Limit",
                    "value": str(limit),
                    "inline": True
                },
                {
                    "name": "Status",
                    "value": "🔴 Blocked",
                    "inline": True
                },
            ],
            "footer": {
                "text": "Litecoin Knowledge Hub - Rate Limiting"
            },
            "timestamp": None
        }
        
        payload = {
            "embeds": [embed]
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(DISCORD_WEBHOOK_URL, json=payload)
            response.raise_for_status()
        
        logger.info(f"Discord rate limit alert sent: {masked_id} hit {limit_type} limit on {endpoint_type}")
        return True
        
    except httpx.HTTPError as e:
        logger.error(f"Failed to send Discord rate limit alert (HTTP error): {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Failed to send Discord rate limit alert: {e}", exc_info=True)
        return False


async def send_cost_throttle_alert(
    stable_identifier: str,
    fingerprint: str,
    estimated_cost: float,
    threshold: float,
    window_seconds: int,
    throttle_seconds: int,
    reason: str = "window_burst",
) -> bool:
    """
    Send a Discord alert when a user hits cost throttling.
    
    Args:
        stable_identifier: The stable user identifier (will be masked)
        fingerprint: The full fingerprint (will be masked)
        estimated_cost: Estimated cost in USD for the request
        threshold: The cost threshold that was exceeded
        window_seconds: The time window in seconds
        throttle_seconds: The throttle duration in seconds
        reason: "window_burst" or "daily_limit"
    
    Returns:
        True if alert was sent successfully, False otherwise
    """
    if not DISCORD_WEBHOOK_URL:
        # Discord webhook not configured, skip silently
        return False
    
    try:
        # Mask identifiers for privacy
        masked_stable_id = _mask_identifier(stable_identifier)
        masked_fingerprint = _mask_identifier(fingerprint)
        
        # Format reason for display
        if reason == "window_burst":
            reason_display = "High Cost Window Burst"
            description = f"A user has exceeded the high cost threshold within the {window_seconds}s window."
        elif reason == "daily_limit":
            reason_display = "Daily Cost Limit"
            description = f"A user has exceeded their daily cost limit per identifier."
        else:
            reason_display = reason.replace("_", " ").title()
            description = f"A user has triggered cost throttling: {reason_display}."
        
        title = f"🚨 Cost Throttle Triggered - {reason_display}"
        color = 0xFF0000  # Red
        
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": [
                {
                    "name": "Stable Identifier",
                    "value": f"`{masked_stable_id}`",
                    "inline": True
                },
                {
                    "name": "Fingerprint",
                    "value": f"`{masked_fingerprint}`",
                    "inline": True
                },
                {
                    "name": "Reason",
                    "value": reason_display,
                    "inline": True
                },
                {
                    "name": "Estimated Cost",
                    "value": f"${estimated_cost:.6f}",
                    "inline": True
                },
                {
                    "name": "Threshold",
                    "value": f"${threshold:.6f}",
                    "inline": True
                },
                {
                    "name": "Window Duration",
                    "value": f"{window_seconds}s",
                    "inline": True
                },
                {
                    "name": "Throttle Duration",
                    "value": f"{throttle_seconds}s",
                    "inline": True
                },
                {
                    "name": "Status",
                    "value": "🔴 Throttled",
                    "inline": True
                },
            ],
            "footer": {
                "text": "Litecoin Knowledge Hub - Cost Throttling"
            },
            "timestamp": None
        }
        
        payload = {
            "embeds": [embed]
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(DISCORD_WEBHOOK_URL, json=payload)
            response.raise_for_status()
        
        logger.info(f"Discord cost throttle alert sent: {masked_stable_id} triggered {reason}")
        return True
        
    except httpx.HTTPError as e:
        logger.error(f"Failed to send Discord cost throttle alert (HTTP error): {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Failed to send Discord cost throttle alert: {e}", exc_info=True)
        return False

