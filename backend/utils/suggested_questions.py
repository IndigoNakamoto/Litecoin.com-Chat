"""
Utility functions for fetching suggested questions from Payload CMS.
"""

import os
import logging
from typing import List, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


async def fetch_suggested_questions(
    payload_url: Optional[str] = None,
    active_only: bool = True
) -> List[Dict]:
    """
    Fetch suggested questions from Payload CMS.
    
    Args:
        payload_url: Payload CMS URL (defaults to PAYLOAD_URL or PAYLOAD_PUBLIC_SERVER_URL env var, or https://cms.lite.space)
        active_only: If True, only fetch active questions (isActive=true)
        
    Returns:
        List of question dictionaries with id, question, order, isActive fields
    """
    if payload_url is None:
        # Check both PAYLOAD_URL and PAYLOAD_PUBLIC_SERVER_URL (docker-compose uses the latter)
        payload_url = os.getenv("PAYLOAD_URL") or os.getenv("PAYLOAD_PUBLIC_SERVER_URL") or "https://cms.lite.space"
    
    # Build query parameters
    query_params = {
        "sort": "order",
        "limit": "500",
    }
    
    if active_only:
        # Payload 3 ignores a JSON-string `where` (it returned every row, so the
        # cache warm-up pre-generated answers for inactive questions); the
        # bracket form is the one its REST API parses.
        query_params["where[isActive][equals]"] = "true"
    
    # Construct URL
    url = f"{payload_url}/api/suggested-questions"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=query_params)
            response.raise_for_status()
            
            data = response.json()
            questions = data.get("docs", [])
            if active_only:
                # Belt and braces: never hand an inactive question to the pre-cache.
                questions = [q for q in questions if q.get("isActive") is not False]
            
            logger.info(f"Fetched {len(questions)} suggested questions from Payload CMS at {url}")
            return questions
            
    except httpx.TimeoutException:
        logger.error(f"Timeout fetching suggested questions from {url}. Is Payload CMS running?")
        return []
    except httpx.HTTPStatusError as e:
        # Check if it's a Cloudflare Tunnel error (530) or other 5xx errors
        if e.response.status_code == 530:
            logger.error(
                f"Cloudflare Tunnel error (530) when fetching from {url}. "
                f"In development, ensure PAYLOAD_PUBLIC_SERVER_URL is set to the local Payload CMS URL (e.g., http://payload_cms:3000). "
                f"Error: {e.response.text[:200]}"
            )
        else:
            logger.error(f"HTTP error {e.response.status_code} fetching suggested questions from {url}: {e.response.text[:200]}")
        return []
    except httpx.ConnectError as e:
        logger.error(
            f"Connection error fetching suggested questions from {url}. "
            f"Is Payload CMS running? In development, use http://payload_cms:3000. Error: {e}"
        )
        return []
    except Exception as e:
        logger.error(f"Error fetching suggested questions from Payload CMS at {url}: {e}", exc_info=True)
        return []

