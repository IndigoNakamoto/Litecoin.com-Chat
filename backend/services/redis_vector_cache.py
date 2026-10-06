"""
Redis Stack Vector Cache

Provides semantic caching using Redis Stack's vector search capabilities.
Uses HNSW index for fast approximate nearest neighbor search with
cosine similarity.

The cache stores rewritten query vectors alongside their responses,
enabling semantic matching for similar queries (not just exact matches).

Features:
- HNSW vector index (1024-dim for stella_en_1.5B_v5)
- Cosine similarity with configurable threshold (default: 0.92)
- LFU eviction via Redis maxmemory-policy
- Persistent storage with optional AOF

Usage:
    cache = RedisVectorCache()
    
    # Check cache
    result = await cache.get(query_vector)
    if result:
        answer, sources = result
    
    # Store in cache
    await cache.set(query_vector, answer, sources)
"""

import os
import re
import json
import hashlib
import logging
from typing import List, Optional, Set, Tuple, Any, Dict
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

# Import metrics if available
try:
    from prometheus_client import Counter, Gauge, Histogram
    
    redis_cache_hits_total = Counter(
        "redis_vector_cache_hits_total",
        "Total Redis vector cache hits"
    )
    redis_cache_misses_total = Counter(
        "redis_vector_cache_misses_total",
        "Total Redis vector cache misses"
    )
    redis_cache_size = Gauge(
        "redis_vector_cache_size",
        "Number of entries in Redis vector cache"
    )
    redis_cache_memory_bytes = Gauge(
        "redis_vector_cache_memory_bytes",
        "Memory usage of Redis vector cache in bytes"
    )
    redis_cache_lookup_seconds = Histogram(
        "redis_vector_cache_lookup_seconds",
        "Redis vector cache lookup latency",
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25]
    )
    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False
    logger.debug("Prometheus metrics not available for Redis cache")


@dataclass
class CacheEntry:
    """Cached query-response entry."""
    query: str
    response: str
    sources: List[Dict[str, Any]]
    similarity: float
    is_grounded: bool = False


# Function words. Content tokens are what distinguish one question from another.
_CACHE_QUESTION_STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "in", "on", "for", "to", "and", "or",
        "what", "is", "are", "was", "were", "does", "do", "did",
        "how", "why", "when", "where", "who", "whom", "which",
        "can", "could", "should", "would", "i", "me", "my", "you", "your",
        "with", "use", "using", "used", "included", "include",
        "about", "tell", "please", "into", "from", "by", "at", "it", "its",
        "be", "as", "that", "this",
    }
)


def cache_question_tokens(text: str) -> Set[str]:
    """Content words of a query after any retrieval-expansion suffix is removed."""
    from backend.utils.litecoin_vocabulary import peel_entity_expansion

    core = peel_entity_expansion(text or "")
    return {
        tok
        for tok in re.findall(r"[a-z0-9]+", core.lower())
        if tok not in _CACHE_QUESTION_STOPWORDS
    }


def same_cached_question(lookup: str, stored: str) -> bool:
    """
    True when ``lookup`` and ``stored`` ask the same thing.

    Equal content-token sets match. So does a one-word paraphrase, where the
    smaller set is contained in the larger and the larger has a single extra
    token. Distinct questions that only share a topic do not match.
    """
    left = cache_question_tokens(lookup)
    right = cache_question_tokens(stored)
    if left == right:
        return True
    if not left or not right:
        return False
    smaller, larger = (left, right) if len(left) <= len(right) else (right, left)
    return smaller <= larger and len(larger - smaller) <= 1


def _payload_ids_from_sources(sources: List[Dict[str, Any]]) -> List[str]:
    """Collect distinct Payload CMS document ids referenced by cached sources."""
    ids: List[str] = []
    for src in sources or []:
        meta = src.get("metadata") if isinstance(src, dict) else None
        if not isinstance(meta, dict):
            continue
        pid = meta.get("payload_id")
        if pid and str(pid) not in ids:
            ids.append(str(pid))
    return ids


class RedisVectorCache:
    """
    Redis Stack vector cache with HNSW index.
    
    Uses Redis Stack's vector search capabilities for semantic caching.
    Queries are matched based on embedding similarity rather than exact match.
    
    Attributes:
        redis_url: Redis Stack connection URL
        index_name: Name of the vector search index
        dimension: Vector dimension (1024 for stella_en_1.5B_v5)
        threshold: Minimum similarity for cache hit (default: 0.92)
    """
    
    INDEX_NAME = "cache:semantic_index"
    KEY_PREFIX = "cache:entry:"
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        index_name: Optional[str] = None,
        dimension: Optional[int] = None,
        threshold: Optional[float] = None,
        ttl_seconds: Optional[int] = None,
    ):
        """
        Initialize Redis vector cache.
        
        Args:
            redis_url: Redis Stack URL (default: REDIS_STACK_URL env var)
            index_name: Index name (default: REDIS_CACHE_INDEX_NAME env var)
            dimension: Vector dimension (default: VECTOR_DIMENSION env var or 1024)
            threshold: Similarity threshold (default: REDIS_CACHE_SIMILARITY_THRESHOLD env var or 0.92)
            ttl_seconds: Per-entry TTL (default: REDIS_CACHE_TTL_SECONDS env var or 7 days; 0 = no expiry)
        """
        self.redis_url = redis_url or os.getenv("REDIS_STACK_URL", "redis://localhost:6379")
        self.index_name = index_name or os.getenv("REDIS_CACHE_INDEX_NAME", self.INDEX_NAME)
        self.dimension = dimension or int(os.getenv("VECTOR_DIMENSION", "1024"))
        self.threshold = threshold or float(os.getenv("REDIS_CACHE_SIMILARITY_THRESHOLD", "0.92"))
        # Per-key TTL so corrected articles cannot be shadowed forever by an
        # old cached answer. 0 disables expiry (LFU eviction only).
        if ttl_seconds is None:
            ttl_seconds = int(os.getenv("REDIS_CACHE_TTL_SECONDS", str(7 * 24 * 3600)))
        self.ttl_seconds = max(0, int(ttl_seconds))
        
        self._client = None
        self._index_created = False
        
        logger.info(
            f"RedisVectorCache initialized: url={self._mask_url(self.redis_url)}, "
            f"index={self.index_name}, dim={self.dimension}, threshold={self.threshold}, "
            f"ttl={self.ttl_seconds}s"
        )
    
    def _mask_url(self, url: str) -> str:
        """Mask password in URL for logging."""
        if "@" in url:
            parts = url.split("@")
            return f"redis://***@{parts[-1]}"
        return url
    
    async def _get_client(self):
        """Get or create Redis client with vector search support."""
        if self._client is None:
            try:
                import redis.asyncio as redis
                
                self._client = redis.from_url(
                    self.redis_url,
                    decode_responses=False,  # Need bytes for vectors
                )
                
                # Test connection
                await self._client.ping()
                logger.info("Redis Stack connection established")
                
                # Ensure index exists
                await self._ensure_index()
                
            except ImportError:
                logger.error("redis package not installed. Install with: pip install redis")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to Redis Stack: {e}")
                raise
        
        return self._client
    
    async def _ensure_index(self):
        """Create vector search index if it doesn't exist."""
        client = self._client
        
        try:
            # Check if index exists
            try:
                await client.ft(self.index_name).info()
                logger.debug(f"Vector index '{self.index_name}' already exists")
                self._index_created = True
                return
            except Exception as e:
                # Index doesn't exist, create it
                logger.debug(f"Index '{self.index_name}' not found, creating it: {e}")
            
            # Create HNSW vector index
            from redis.commands.search.field import VectorField, TextField

            try:  # redis-py >= 6 (snake_case module)
                from redis.commands.search.index_definition import IndexDefinition, IndexType
            except ImportError:  # redis-py 5.x ships the camelCase module name
                from redis.commands.search.indexDefinition import IndexDefinition, IndexType
            
            schema = [
                VectorField(
                    "embedding",
                    "HNSW",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": self.dimension,
                        "DISTANCE_METRIC": "COSINE",
                        "INITIAL_CAP": 1000,
                        "M": 16,
                        "EF_CONSTRUCTION": 200,
                    },
                ),
                TextField("query"),
                TextField("response"),
            ]
            
            definition = IndexDefinition(
                prefix=[self.KEY_PREFIX],
                index_type=IndexType.HASH,
            )
            
            await client.ft(self.index_name).create_index(
                schema,
                definition=definition,
            )
            
            logger.info(f"Created vector index '{self.index_name}' (dim={self.dimension})")
            self._index_created = True
            
        except Exception as e:
            # If index creation fails, reset flag to retry next time
            self._index_created = False
            logger.error(f"Failed to create vector index: {e}", exc_info=True)
            raise
    
    def _vector_to_bytes(self, vector: List[float]) -> bytes:
        """Convert vector to bytes for Redis storage."""
        return np.array(vector, dtype=np.float32).tobytes()
    
    def _bytes_to_vector(self, data: bytes) -> List[float]:
        """Convert bytes back to vector."""
        return np.frombuffer(data, dtype=np.float32).tolist()
    
    def _generate_key(self, vector: List[float]) -> str:
        """Generate cache key from vector hash."""
        vector_bytes = self._vector_to_bytes(vector)
        hash_value = hashlib.md5(vector_bytes).hexdigest()
        return f"{self.KEY_PREFIX}{hash_value}"
    
    async def get(
        self,
        query_vector: List[float],
        k: int = 1,
    ) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        """
        Search cache for similar query.
        
        Args:
            query_vector: Query embedding vector
            k: Number of results to return (default: 1)
            
        Returns:
            Tuple of (response, sources) if cache hit, None if miss
        """
        entry = await self.get_entry(query_vector, k=k)
        if entry is None:
            return None
        return entry.response, entry.sources

    async def get_entry(
        self,
        query_vector: List[float],
        k: int = 1,
        query_text: Optional[str] = None,
    ) -> Optional[CacheEntry]:
        """
        Search cache for similar query and return the full entry.

        Unlike `get`, this preserves `is_grounded` so a cached web-supplemented
        answer is replayed with the same provenance flag it was stored with.

        When ``query_text`` is set, a neighbor past the cosine threshold is
        still a miss if it asks a different question.
        """
        import time
        start_time = time.time()
        
        try:
            client = await self._get_client()
            
            # Ensure index exists (in case it was lost after restart)
            await self._ensure_index()
            
            from redis.commands.search.query import Query
            
            # Build KNN query
            query_bytes = self._vector_to_bytes(query_vector)
            
            q = (
                Query(f"*=>[KNN {k} @embedding $vec AS score]")
                .return_fields("query", "response", "sources", "is_grounded", "score")
                .sort_by("score")
                .dialect(2)
            )
            
            results = await client.ft(self.index_name).search(
                q,
                query_params={"vec": query_bytes},
            )
            
            latency = time.time() - start_time
            if METRICS_ENABLED:
                redis_cache_lookup_seconds.observe(latency)
            
            if not results.docs:
                if METRICS_ENABLED:
                    redis_cache_misses_total.inc()
                logger.debug(f"Cache miss (no results) in {latency:.3f}s")
                return None
            
            # Check similarity threshold
            # Redis returns cosine distance where: distance = 1 - cosine_similarity
            # For normalized vectors: distance 0 = identical (similarity 1), distance 2 = opposite (similarity -1)
            # Correct conversion: similarity = 1 - distance
            best_match = results.docs[0]
            distance = float(best_match.score)
            similarity = 1 - distance
            
            if similarity < self.threshold:
                if METRICS_ENABLED:
                    redis_cache_misses_total.inc()
                logger.debug(
                    f"Cache miss (similarity {similarity:.3f} < threshold {self.threshold}) "
                    f"in {latency:.3f}s"
                )
                return None
            
            response = best_match.response
            if isinstance(response, bytes):
                response = response.decode("utf-8")
            
            sources_raw = getattr(best_match, "sources", None)
            if isinstance(sources_raw, bytes):
                sources_raw = sources_raw.decode("utf-8")
            sources = json.loads(sources_raw) if sources_raw else []

            grounded_raw = getattr(best_match, "is_grounded", None)
            if isinstance(grounded_raw, bytes):
                grounded_raw = grounded_raw.decode("utf-8")
            is_grounded = str(grounded_raw or "0") == "1"

            query_raw = getattr(best_match, "query", "")
            if isinstance(query_raw, bytes):
                query_raw = query_raw.decode("utf-8")

            if query_text and not same_cached_question(query_text, query_raw or ""):
                if METRICS_ENABLED:
                    redis_cache_misses_total.inc()
                logger.info(
                    "Semantic cache rejected: similarity=%.3f lookup=%r stored=%r",
                    similarity,
                    query_text[:160],
                    (query_raw or "")[:160],
                )
                return None

            if METRICS_ENABLED:
                redis_cache_hits_total.inc()
            
            logger.debug(
                f"Cache hit (similarity {similarity:.3f}, grounded={is_grounded}) in {latency:.3f}s"
            )
            return CacheEntry(
                query=query_raw or "",
                response=response,
                sources=sources,
                similarity=similarity,
                is_grounded=is_grounded,
            )
            
        except Exception as e:
            logger.error(f"Redis cache get error: {e}")
            if METRICS_ENABLED:
                redis_cache_misses_total.inc()
            return None
    
    async def set(
        self,
        query_vector: List[float],
        query_text: str,
        response: str,
        sources: List[Dict[str, Any]],
        is_grounded: bool = False,
    ) -> bool:
        """
        Store entry in cache.
        
        Args:
            query_vector: Query embedding vector
            query_text: Original query text (for debugging)
            response: Response to cache
            sources: Source documents
            is_grounded: Whether the answer used web search grounding
            
        Returns:
            True if stored successfully, False otherwise
        """
        try:
            client = await self._get_client()
            
            key = self._generate_key(query_vector)
            
            # Serialize sources
            sources_json = json.dumps(sources, default=str)
            payload_ids = _payload_ids_from_sources(sources)
            
            # Store as hash with vector
            await client.hset(
                key,
                mapping={
                    "embedding": self._vector_to_bytes(query_vector),
                    "query": query_text.encode("utf-8"),
                    "response": response.encode("utf-8"),
                    "sources": sources_json.encode("utf-8"),
                    "is_grounded": b"1" if is_grounded else b"0",
                    "payload_ids": " ".join(payload_ids).encode("utf-8"),
                },
            )
            if self.ttl_seconds > 0:
                await client.expire(key, self.ttl_seconds)
            
            logger.debug(f"Cached response for query: {query_text[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Redis cache set error: {e}")
            return False

    async def invalidate_by_payload_id(self, payload_id: str) -> int:
        """
        Delete every cached answer that cited the given Payload CMS document.

        Called from the CMS webhook on update/unpublish/delete so a corrected
        article is never shadowed by a stale cached answer.

        Returns:
            Number of entries removed.
        """
        if not payload_id:
            return 0
        target = str(payload_id)
        removed = 0
        try:
            client = await self._get_client()
            async for key in client.scan_iter(match=f"{self.KEY_PREFIX}*"):
                raw = await client.hget(key, "payload_ids")
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                if target in raw.split():
                    await client.delete(key)
                    removed += 1
            if removed:
                logger.info(
                    "Invalidated %d semantic cache entr%s citing payload_id=%s",
                    removed,
                    "y" if removed == 1 else "ies",
                    target,
                )
            return removed
        except Exception as e:
            logger.error(f"Redis cache invalidate error for payload_id={target}: {e}")
            return removed
    
    async def delete(self, query_vector: List[float]) -> bool:
        """Delete entry from cache."""
        try:
            client = await self._get_client()
            key = self._generate_key(query_vector)
            await client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis cache delete error: {e}")
            return False
    
    async def clear(self) -> bool:
        """Clear all cache entries."""
        try:
            client = await self._get_client()
            
            # Get all keys with prefix
            keys = []
            async for key in client.scan_iter(match=f"{self.KEY_PREFIX}*"):
                keys.append(key)
            
            if keys:
                await client.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries")
            
            return True
            
        except Exception as e:
            logger.error(f"Redis cache clear error: {e}")
            return False
    
    async def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            client = await self._get_client()
            
            # Count entries
            count = 0
            async for _ in client.scan_iter(match=f"{self.KEY_PREFIX}*"):
                count += 1
            
            # Get memory info
            info = await client.info("memory")
            used_memory = info.get("used_memory", 0)
            
            # Get index info
            try:
                index_info = await client.ft(self.index_name).info()
                num_docs = int(index_info.get("num_docs", 0))
            except Exception:
                num_docs = count
            
            if METRICS_ENABLED:
                redis_cache_size.set(count)
                redis_cache_memory_bytes.set(used_memory)
            
            return {
                "entries": count,
                "indexed_docs": num_docs,
                "memory_bytes": used_memory,
                "dimension": self.dimension,
                "threshold": self.threshold,
                "index_name": self.index_name,
            }
            
        except Exception as e:
            logger.error(f"Redis cache stats error: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> bool:
        """Check if Redis Stack is healthy."""
        try:
            client = await self._get_client()
            await client.ping()
            
            # Check if vector search is available
            try:
                await client.ft(self.index_name).info()
            except Exception:
                # Index might not exist yet, but Redis is healthy
                pass
            
            return True
            
        except Exception as e:
            logger.warning(f"Redis Stack health check failed: {e}")
            return False
    
    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.debug("Redis connection closed")

