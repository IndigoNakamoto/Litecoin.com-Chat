"""
LLM Observability integration using LangSmith.

This module provides integration with LangSmith for comprehensive LLM tracing,
token counting, and cost tracking.
"""

import os
import logging
from typing import Optional, Dict, Any
from functools import wraps

logger = logging.getLogger(__name__)

# LangSmith integration
_langsmith_configured = False
_langsmith_tracer = None


def setup_langsmith(
    api_key: Optional[str] = None,
    project_name: Optional[str] = None,
    environment: Optional[str] = None,
) -> bool:
    """
    Configure LangSmith for LLM observability.
    
    Args:
        api_key: LangSmith API key (defaults to LANGCHAIN_API_KEY env var)
        project_name: Project name for LangSmith (defaults to LANGCHAIN_PROJECT env var)
        environment: Environment name (defaults to LANGCHAIN_ENVIRONMENT env var)
    
    Returns:
        True if LangSmith is successfully configured, False otherwise
    """
    global _langsmith_configured, _langsmith_tracer
    
    try:
        # Set environment variables if provided
        if api_key:
            os.environ["LANGCHAIN_API_KEY"] = api_key
        if project_name:
            os.environ["LANGCHAIN_PROJECT"] = project_name
        if environment:
            os.environ["LANGCHAIN_ENVIRONMENT"] = environment
        
        # Check if LangSmith is configured
        langchain_api_key = os.getenv("LANGCHAIN_API_KEY")
        langchain_project = os.getenv("LANGCHAIN_PROJECT", "litecoin-knowledge-hub")
        langchain_env = os.getenv("LANGCHAIN_ENVIRONMENT", os.getenv("ENVIRONMENT", "development"))
        
        if not langchain_api_key:
            logger.warning(
                "LangSmith API key not found. Set LANGCHAIN_API_KEY environment variable "
                "to enable LLM observability."
            )
            return False
        
        # Set default project and environment
        os.environ["LANGCHAIN_PROJECT"] = langchain_project
        os.environ["LANGCHAIN_ENVIRONMENT"] = langchain_env
        
        # LangSmith is automatically enabled when LANGCHAIN_API_KEY is set
        # LangChain will use it for tracing automatically
        _langsmith_configured = True
        
        logger.info(
            f"LangSmith observability configured: project={langchain_project}, "
            f"environment={langchain_env}"
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to configure LangSmith: {e}", exc_info=True)
        return False


def is_langsmith_configured() -> bool:
    """Check if LangSmith is configured."""
    return _langsmith_configured


def get_langsmith_config() -> Dict[str, Any]:
    """Get current LangSmith configuration."""
    return {
        "configured": _langsmith_configured,
        "api_key_set": bool(os.getenv("LANGCHAIN_API_KEY")),
        "project": os.getenv("LANGCHAIN_PROJECT", "not-set"),
        "environment": os.getenv("LANGCHAIN_ENVIRONMENT", "not-set"),
    }


def track_llm_metrics(
    model: str,
    operation: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    duration_seconds: Optional[float] = None,
    status: str = "success",
):
    """
    Track LLM metrics for observability.
    
    This function should be called after LLM operations to record metrics.
    It integrates with both Prometheus metrics and LangSmith (if configured).
    
    Args:
        model: LLM model name (e.g., "gemini-2.0-flash-lite")
        operation: Operation type (e.g., "generate", "embed", "retrieve")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cost_usd: Cost in USD for the operation
        duration_seconds: Duration of the operation in seconds
        status: Status of the operation ("success" or "error")
    """
    try:
        from .metrics import (
            llm_requests_total,
            llm_tokens_total,
            llm_cost_usd_total,
            llm_request_duration_seconds,
        )
        
        # Record request count
        llm_requests_total.labels(
            model=model,
            operation=operation,
            status=status,
        ).inc()
        
        # Record tokens
        if input_tokens:
            llm_tokens_total.labels(
                model=model,
                token_type="input",
            ).inc(input_tokens)
        
        if output_tokens:
            llm_tokens_total.labels(
                model=model,
                token_type="output",
            ).inc(output_tokens)
        
        # Record cost
        if cost_usd:
            llm_cost_usd_total.labels(
                model=model,
                operation=operation,
            ).inc(cost_usd)
            try:
                from .cost_tracker import record_llm_cost
            except ImportError:
                record_llm_cost = None

            if record_llm_cost:
                record_llm_cost(model, operation, cost_usd)
        
        # Record duration
        if duration_seconds:
            llm_request_duration_seconds.labels(
                model=model,
                operation=operation,
            ).observe(duration_seconds)
    
    except Exception as e:
        logger.error(f"Failed to track LLM metrics: {e}", exc_info=True)


def estimate_gemini_cost(
    input_tokens: int,
    output_tokens: int,
    model: str = "gemini-2.0-flash-lite",
) -> float:
    """
    Estimate cost for Gemini API calls.
    
    Pricing as of 2024-2025:
    - gemini-3.1-flash-lite-preview: $0.10 per 1M input tokens, $0.40 per 1M output tokens (assumed same as 2.5 lite)
    - gemini-2.5-flash-lite-preview-09-2025: $0.10 per 1M input tokens, $0.40 per 1M output tokens
    - gemini-2.0-flash-lite: $0.075 per 1M input tokens, $0.30 per 1M output tokens
    - gemini-pro: $0.50 per 1M input tokens, $1.50 per 1M output tokens
    - gemini-1.5-pro: $1.25 per 1M input tokens, $5.00 per 1M output tokens
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name
    
    Returns:
        Estimated cost in USD
    """
    # Pricing per 1M tokens
    pricing = {
        "gemini-3.1-flash-lite-preview": {"input": 0.10, "output": 0.40},
        "gemini-2.5-flash-lite-preview-09-2025": {"input": 0.10, "output": 0.40},
        "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
        "gemini-pro": {"input": 0.50, "output": 1.50},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    }
    
    # Match model name (handle partial matches for preview versions)
    model_pricing = None
    for model_key, prices in pricing.items():
        if model_key in model or model in model_key:
            model_pricing = prices
            break
    
    # Default to gemini-3.1-flash-lite-preview pricing if not found (since that's what's being used)
    if model_pricing is None:
        logger.warning(f"Unknown model '{model}', using gemini-3.1-flash-lite-preview pricing")
        model_pricing = pricing["gemini-3.1-flash-lite-preview"]
    
    input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
    
    return input_cost + output_cost

