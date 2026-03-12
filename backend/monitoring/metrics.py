"""
Prometheus metrics for application monitoring.

This module defines all metrics used for monitoring the Litecoin Knowledge Hub:
- HTTP request metrics
- RAG pipeline metrics
- LLM observability metrics
- Vector store metrics
- Webhook processing metrics
"""

import time
from typing import Optional
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    REGISTRY,
    CONTENT_TYPE_LATEST,
)
from prometheus_client.openmetrics.exposition import generate_latest as generate_latest_openmetrics


# HTTP Request Metrics
request_count_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)

request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "status_code"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# RAG Pipeline Metrics
rag_query_duration_seconds = Histogram(
    "rag_query_duration_seconds",
    "RAG query processing duration in seconds",
    ["query_type", "cache_hit"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

rag_cache_hits_total = Counter(
    "rag_cache_hits_total",
    "Total number of RAG cache hits",
    ["cache_type"],
)

rag_cache_misses_total = Counter(
    "rag_cache_misses_total",
    "Total number of RAG cache misses",
    ["cache_type"],
)

rag_retrieval_duration_seconds = Histogram(
    "rag_retrieval_duration_seconds",
    "Vector store retrieval duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

rag_documents_retrieved_total = Histogram(
    "rag_documents_retrieved_total",
    "Number of documents retrieved per query",
    buckets=[1, 5, 10, 15, 20, 25, 30],
)

# Detailed RAG Pipeline Timing Metrics
rag_query_rewrite_duration_seconds = Histogram(
    "rag_query_rewrite_duration_seconds",
    "Query rewriting duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

rag_embedding_generation_duration_seconds = Histogram(
    "rag_embedding_generation_duration_seconds",
    "Query embedding generation duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

rag_vector_search_duration_seconds = Histogram(
    "rag_vector_search_duration_seconds",
    "Vector search duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

rag_bm25_search_duration_seconds = Histogram(
    "rag_bm25_search_duration_seconds",
    "BM25 search duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

rag_sparse_rerank_duration_seconds = Histogram(
    "rag_sparse_rerank_duration_seconds",
    "Sparse re-ranking duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

rag_llm_generation_duration_seconds = Histogram(
    "rag_llm_generation_duration_seconds",
    "LLM answer generation duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# Suggested Question Cache Metrics
suggested_question_cache_hits_total = Counter(
    "suggested_question_cache_hits_total",
    "Total number of suggested question cache hits",
    ["cache_type"],
)

suggested_question_cache_misses_total = Counter(
    "suggested_question_cache_misses_total",
    "Total number of suggested question cache misses",
    ["cache_type"],
)

suggested_question_cache_lookup_duration_seconds = Histogram(
    "suggested_question_cache_lookup_duration_seconds",
    "Suggested question cache lookup duration in seconds",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)

suggested_question_cache_size = Gauge(
    "suggested_question_cache_size",
    "Number of cached suggested questions",
)

suggested_question_cache_refresh_duration_seconds = Histogram(
    "suggested_question_cache_refresh_duration_seconds",
    "Suggested question cache refresh duration in seconds",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

suggested_question_cache_refresh_errors_total = Counter(
    "suggested_question_cache_refresh_errors_total",
    "Total number of errors during suggested question cache refresh",
)

# LLM Observability Metrics
llm_requests_total = Counter(
    "llm_requests_total",
    "Total number of LLM API requests",
    ["model", "operation", "status"],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total number of tokens processed by LLM",
    ["model", "token_type"],  # token_type: "input" or "output"
)

llm_cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Total cost in USD for LLM API calls",
    ["model", "operation"],
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM API request duration in seconds",
    ["model", "operation"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# LLM Spend Limit Metrics
llm_daily_cost_usd = Gauge(
    "llm_daily_cost_usd",
    "Current daily LLM cost in USD"
)

llm_hourly_cost_usd = Gauge(
    "llm_hourly_cost_usd",
    "Current hourly LLM cost in USD"
)

llm_daily_limit_usd = Gauge(
    "llm_daily_limit_usd",
    "Daily LLM spend limit in USD"
)

llm_hourly_limit_usd = Gauge(
    "llm_hourly_limit_usd",
    "Hourly LLM spend limit in USD"
)

llm_spend_limit_rejections_total = Counter(
    "llm_spend_limit_rejections_total",
    "Total number of requests rejected due to spend limits",
    ["limit_type"],  # "daily" or "hourly"
)

# Vector Store Metrics
vector_store_documents_total = Gauge(
    "vector_store_documents_total",
    "Total number of documents in the vector store",
    ["status"],  # status: "published", "draft", "total"
)

vector_store_size_bytes = Gauge(
    "vector_store_size_bytes",
    "Size of vector store in bytes",
)

vector_store_health = Gauge(
    "vector_store_health",
    "Vector store health status (1 = healthy, 0 = unhealthy)",
)

# Webhook Processing Metrics
webhook_processing_total = Counter(
    "webhook_processing_total",
    "Total number of webhook processing attempts",
    ["source", "operation", "status"],
)

webhook_processing_duration_seconds = Histogram(
    "webhook_processing_duration_seconds",
    "Webhook processing duration in seconds",
    ["source", "operation"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# Application Health Metrics
application_health = Gauge(
    "application_health",
    "Application health status (1 = healthy, 0 = unhealthy)",
    ["service"],  # service: "backend", "vector_store", "mongodb", "llm"
)

# Active Connections
active_connections = Gauge(
    "active_connections",
    "Number of active connections",
    ["connection_type"],
)

# User Questions Metrics
user_questions_total = Counter(
    "user_questions_total",
    "Total number of user questions asked",
    ["endpoint_type"],  # endpoint_type: "chat" or "stream"
)

user_questions_analyzed_total = Counter(
    "user_questions_analyzed_total",
    "Total number of user questions that have been analyzed",
)

# Gauge for total questions from MongoDB (updated periodically)
user_questions_count_from_db = Gauge(
    "user_questions_count_from_db",
    "Total number of user questions from MongoDB database",
    ["endpoint_type"],  # endpoint_type: "chat", "stream", or "total"
)

# Knowledge Gap Flywheel Metrics
knowledge_candidates_total = Counter(
    "knowledge_candidates_total",
    "Total knowledge gap candidates created",
    ["trigger"],  # trigger: "grounding", "no_kb_sources", "provenance_marker"
)

knowledge_candidates_approved_total = Counter(
    "knowledge_candidates_approved_total",
    "Total knowledge gap candidates approved by admin",
)

knowledge_candidates_rejected_total = Counter(
    "knowledge_candidates_rejected_total",
    "Total knowledge gap candidates rejected by admin",
)

knowledge_candidates_published_total = Counter(
    "knowledge_candidates_published_total",
    "Total knowledge gap candidates published as CMS drafts",
)

knowledge_candidates_deduped_total = Counter(
    "knowledge_candidates_deduped_total",
    "Total knowledge gap candidates deduplicated (frequency incremented)",
)

# Rate limiting metrics
rate_limit_rejections_total = Counter(
    "rate_limit_rejections_total",
    "Total number of requests rejected due to rate limiting",
    ["endpoint_type"],  # e.g. "chat", "chat_stream"
)

rate_limit_bans_total = Counter(
    "rate_limit_bans_total",
    "Total number of progressive bans applied due to rate limit violations",
    ["endpoint_type"],  # e.g. "chat", "chat_stream"
)

rate_limit_violations_total = Counter(
    "rate_limit_violations_total",
    "Total number of rate limit violations",
    ["endpoint_type"],  # e.g. "chat", "chat_stream"
)

# Cost-Based Throttling Metrics
cost_throttle_triggers_total = Counter(
    "cost_throttle_triggers_total",
    "Number of times cost throttling was triggered",
    ["reason"],  # "window_burst", "daily_limit", "already_throttled"
)

cost_throttle_active_users = Gauge(
    "cost_throttle_active_users",
    "Number of fingerprints currently throttled"
)

cost_recorded_usd_total = Counter(
    "cost_recorded_usd_total",
    "Total USD cost recorded (estimated + actual)",
    ["type"],  # "estimated", "actual"
)

# Rate Limiting Precision Metrics
rate_limit_retry_after_seconds = Histogram(
    "rate_limit_retry_after_seconds",
    "Retry-After values returned to clients",
    ["identifier", "window"],  # identifier: "per_user", "global"; window: "minute", "hour"
    buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600],
)

rate_limit_checks_total = Counter(
    "rate_limit_checks_total",
    "Total number of rate limit checks performed",
    ["check_type", "result"],  # check_type: "individual", "global"; result: "allowed", "rejected"
)

# Challenge System Metrics
challenge_generation_total = Counter(
    "challenge_generation_total",
    "Total challenges generated",
    ["result"],  # "success", "rate_limited", "banned", "limit_exceeded"
)

challenge_validation_failures_total = Counter(
    "challenge_validation_failures_total",
    "Failed challenge validations",
    ["reason"],  # "missing", "expired", "mismatch", "consumed", "invalid_format"
)

challenge_validations_total = Counter(
    "challenge_validations_total",
    "Total challenge validations attempted",
    ["result"],  # "success", "failure"
)

challenge_reuse_attempts_total = Counter(
    "challenge_reuse_attempts_total",
    "Total attempts to reuse challenges (replay attacks)",
)

# Atomic Operation Metrics
lua_script_executions_total = Counter(
    "lua_script_executions_total",
    "Total Lua script executions",
    ["script_name", "result"],  # script_name: "sliding_window", "cost_throttle", "record_cost"; result: "success", "error"
)

lua_script_duration_seconds = Histogram(
    "lua_script_duration_seconds",
    "Lua script execution duration in seconds",
    ["script_name"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)


def setup_metrics():
    """Initialize metrics registry. Called at application startup."""
    # Seed counters that require persisted state (e.g., lifetime LLM costs).
    try:
        from .cost_tracker import preload_prometheus_counters
    except ImportError:
        preload_prometheus_counters = None

    if preload_prometheus_counters:
        preload_prometheus_counters()


def get_metrics_registry():
    """Get the Prometheus metrics registry."""
    return REGISTRY


def generate_metrics_response(format: str = "prometheus"):
    """
    Generate metrics response in the specified format.
    
    Args:
        format: Either "prometheus" or "openmetrics"
    
    Returns:
        Tuple of (metrics_bytes, content_type)
    """
    if format == "openmetrics":
        return generate_latest_openmetrics(REGISTRY), CONTENT_TYPE_LATEST
    else:
        return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


class MetricsContext:
    """Context manager for timing operations and recording metrics."""
    
    def __init__(
        self,
        histogram: Histogram,
        counter: Optional[Counter] = None,
        labels: Optional[dict] = None,
    ):
        self.histogram = histogram
        self.counter = counter
        self.labels = labels or {}
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.histogram.labels(**self.labels).observe(duration)
        if self.counter:
            status = "success" if exc_type is None else "error"
            self.counter.labels(**{**self.labels, "status": status}).inc()

