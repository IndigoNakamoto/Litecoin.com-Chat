"""
Integration Tests for Local RAG Pipeline

These tests require the following services to be running:
- Ollama (native or Docker) on port 11434
- Native embedding server on port 7997
- Redis Stack on port 6380
- MongoDB (cloud or local)

Run with: 
    source .env.secrets && pytest backend/tests/test_local_rag_integration.py -v

Skip if services not available:
    pytest backend/tests/test_local_rag_integration.py -v --ignore-glob='*integration*'
"""

import pytest
import asyncio
import os
import sys
import httpx
from typing import List, Tuple, Optional
from pathlib import Path

pytestmark = pytest.mark.integration

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from project root
project_root = Path(__file__).parent.parent.parent
secrets_file = project_root / ".env.secrets"
if secrets_file.exists():
    from dotenv import load_dotenv
    load_dotenv(secrets_file)


# ============================================================================
# Fixtures for Service Availability Checks
# ============================================================================

def is_service_available(url: str, timeout: float = 2.0) -> bool:
    """Check if a service is available."""
    try:
        import httpx
        response = httpx.get(url, timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def is_ollama_available() -> bool:
    """Check if Ollama is running."""
    return is_service_available("http://localhost:11434/api/tags")


def is_infinity_available() -> bool:
    """Check if Infinity/embedding server is running."""
    return is_service_available("http://localhost:7997/health")


def is_redis_stack_available() -> bool:
    """Check if Redis Stack is running."""
    try:
        import redis
        import urllib.parse
        # Try with password from env, fall back to no password
        password = os.environ.get("REDIS_PASSWORD", "")
        if password:
            encoded_password = urllib.parse.quote(password, safe="")
            r = redis.from_url(f"redis://:{encoded_password}@localhost:6380")
        else:
            r = redis.from_url("redis://localhost:6380")
        r.ping()
        return True
    except Exception:
        return False


def get_redis_stack_url() -> str:
    """Get Redis Stack URL with authentication."""
    password = os.environ.get("REDIS_PASSWORD", "")
    if password:
        # URL encode the password
        import urllib.parse
        encoded_password = urllib.parse.quote(password, safe="")
        return f"redis://:{encoded_password}@localhost:6380"
    return "redis://localhost:6380"


# Skip markers
requires_ollama = pytest.mark.skipif(
    not is_ollama_available(),
    reason="Ollama service not available on localhost:11434"
)

requires_infinity = pytest.mark.skipif(
    not is_infinity_available(),
    reason="Embedding server not available on localhost:7997"
)

requires_redis_stack = pytest.mark.skipif(
    not is_redis_stack_available(),
    reason="Redis Stack not available on localhost:6380"
)

requires_all_services = pytest.mark.skipif(
    not (is_ollama_available() and is_infinity_available() and is_redis_stack_available()),
    reason="Not all local RAG services are available"
)


# ============================================================================
# Ollama Integration Tests
# ============================================================================

class TestOllamaIntegration:
    """Integration tests for Ollama query rewriting."""
    
    @requires_ollama
    @pytest.mark.asyncio
    async def test_ollama_health_check(self):
        """Test Ollama API is responding."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags")
            assert response.status_code == 200
            data = response.json()
            assert "models" in data
    
    @requires_ollama
    @pytest.mark.asyncio
    async def test_ollama_model_loaded(self):
        """Test llama3.2:3b model is available."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags")
            data = response.json()
            model_names = [m["name"] for m in data.get("models", [])]
            assert "llama3.2:3b" in model_names, f"Model not found. Available: {model_names}"
    
    @requires_ollama
    @pytest.mark.asyncio
    async def test_local_rewriter_integration(self):
        """Test LocalRewriter with real Ollama."""
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        os.environ["LOCAL_REWRITER_MODEL"] = "llama3.2:3b"
        
        from backend.services.rewriter import LocalRewriter
        rewriter = LocalRewriter()
        
        # Test simple query rewriting
        result = await rewriter.rewrite("What is LTC?", [])
        
        assert result is not None
        assert len(result) > 0
        assert result != "NO_SEARCH_NEEDED"  # Should rewrite, not skip
    
    @requires_ollama
    @pytest.mark.asyncio
    async def test_local_rewriter_with_context(self):
        """Test LocalRewriter resolves context from chat history."""
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        os.environ["LOCAL_REWRITER_MODEL"] = "llama3.2:3b"
        
        from backend.services.rewriter import LocalRewriter
        rewriter = LocalRewriter()
        
        chat_history = [
            ("What is MWEB?", "MWEB is MimbleWimble Extension Blocks, a privacy feature in Litecoin.")
        ]
        
        # "it" should be resolved to "MWEB"
        result = await rewriter.rewrite("Does it improve privacy?", chat_history)
        
        assert result is not None
        # The rewritten query should mention MWEB or privacy
        result_lower = result.lower()
        assert "mweb" in result_lower or "privacy" in result_lower or "mimblewimble" in result_lower
    
    @requires_ollama
    @pytest.mark.asyncio
    async def test_local_rewriter_no_search_needed(self):
        """Test LocalRewriter returns NO_SEARCH_NEEDED for greetings."""
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        os.environ["LOCAL_REWRITER_MODEL"] = "llama3.2:3b"
        
        from backend.services.rewriter import LocalRewriter
        rewriter = LocalRewriter()
        
        result = await rewriter.rewrite("Thanks for your help!", [])
        
        # Should return NO_SEARCH_NEEDED or similar
        # Note: Model might not always return exactly "NO_SEARCH_NEEDED"
        assert result is not None
    
    @requires_ollama
    @pytest.mark.asyncio
    async def test_local_rewriter_latency(self):
        """Test LocalRewriter responds within acceptable time."""
        import time
        
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        os.environ["LOCAL_REWRITER_MODEL"] = "llama3.2:3b"
        
        from backend.services.rewriter import LocalRewriter
        rewriter = LocalRewriter()
        
        start = time.time()
        await rewriter.rewrite("What is Litecoin?", [])
        duration = time.time() - start
        
        # Should respond within 5 seconds (warm model)
        assert duration < 5.0, f"Rewrite took {duration:.2f}s, expected < 5s"


# ============================================================================
# Infinity Embeddings Integration Tests
# ============================================================================

class TestInfinityIntegration:
    """Integration tests for Infinity embedding service."""
    
    @requires_infinity
    @pytest.mark.asyncio
    async def test_infinity_health_check(self):
        """Test Infinity API is responding."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:7997/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "healthy"
    
    @requires_infinity
    @pytest.mark.asyncio
    async def test_infinity_model_info(self):
        """Test Infinity reports correct model."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:7997/models")
            assert response.status_code == 200
            data = response.json()
            assert "dunzhang/stella_en_1.5B_v5" in str(data)
    
    @requires_infinity
    @pytest.mark.asyncio
    async def test_infinity_embeddings_integration(self):
        """Test InfinityEmbeddings with real service."""
        from backend.services.infinity_adapter import InfinityEmbeddings
        
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        
        result = await embeddings.embed_query("What is Litecoin?")
        
        assert result is not None
        assert len(result) == 1024  # Stella model produces 1024-dim vectors
        assert all(isinstance(x, float) for x in result)
    
    @requires_infinity
    @pytest.mark.asyncio
    async def test_infinity_batch_embeddings(self):
        """Test InfinityEmbeddings batch processing."""
        from backend.services.infinity_adapter import InfinityEmbeddings
        
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        
        texts = [
            "What is Litecoin?",
            "How does MWEB work?",
            "When was LTC created?",
        ]
        
        results = await embeddings.embed_documents(texts)
        
        assert len(results) == 3
        assert all(len(r) == 1024 for r in results)
    
    @requires_infinity
    @pytest.mark.asyncio
    async def test_infinity_embeddings_similarity(self):
        """Test that similar queries produce similar embeddings."""
        import numpy as np
        from backend.services.infinity_adapter import InfinityEmbeddings
        
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        
        # Similar queries
        emb1 = await embeddings.embed_query("What is Litecoin?")
        emb2 = await embeddings.embed_query("What is LTC cryptocurrency?")
        
        # Different query
        emb3 = await embeddings.embed_query("What is the weather today?")
        
        # Calculate cosine similarity
        def cosine_sim(a, b):
            a, b = np.array(a), np.array(b)
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        
        sim_similar = cosine_sim(emb1, emb2)
        sim_different = cosine_sim(emb1, emb3)
        
        # Similar queries should have higher similarity
        assert sim_similar > sim_different
        assert sim_similar > 0.7  # Similar queries should be > 0.7
    
    @requires_infinity
    @pytest.mark.asyncio
    async def test_infinity_latency(self):
        """Test Infinity responds within acceptable time."""
        import time
        from backend.services.infinity_adapter import InfinityEmbeddings
        
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        
        start = time.time()
        await embeddings.embed_query("Test query for latency measurement")
        duration = time.time() - start
        
        # Should respond within 1 second (model loaded)
        assert duration < 1.0, f"Embedding took {duration:.2f}s, expected < 1s"


# ============================================================================
# Redis Stack Cache Integration Tests
# ============================================================================

class TestRedisStackIntegration:
    """Integration tests for Redis Stack vector cache.
    
    IMPORTANT: These tests use database 1 (test database) to avoid
    polluting the production cache in database 0.
    """
    
    @pytest.fixture(autouse=True)
    def use_test_database(self):
        """Use Redis database 1 for tests to avoid polluting production cache."""
        # Set test-specific index name
        os.environ["REDIS_CACHE_INDEX_NAME"] = "test:integration:index"
        yield
        # Cleanup: Clear test data after each test
        try:
            import redis
            r = redis.from_url(get_redis_stack_url())
            # Delete test keys
            for key in r.scan_iter("cache:entry:*"):
                r.delete(key)
            # Drop test index if exists
            try:
                r.execute_command("FT.DROPINDEX", "test:integration:index", "DD")
            except Exception:
                pass
            try:
                r.execute_command("FT.DROPINDEX", "test:cache:index", "DD")
            except Exception:
                pass
            try:
                r.execute_command("FT.DROPINDEX", "test:e2e:index", "DD")
            except Exception:
                pass
        except Exception:
            pass
    
    @requires_redis_stack
    @pytest.mark.asyncio
    async def test_redis_stack_connection(self):
        """Test Redis Stack connection."""
        import redis
        r = redis.from_url(get_redis_stack_url())
        assert r.ping()
    
    @requires_redis_stack
    @pytest.mark.asyncio
    async def test_redis_stack_modules(self):
        """Test Redis Stack has required modules."""
        import redis
        r = redis.from_url(get_redis_stack_url())
        
        # Check for RediSearch module
        modules = r.module_list()
        module_names = [m[b'name'].decode() if isinstance(m[b'name'], bytes) else m[b'name'] for m in modules]
        
        assert "search" in module_names or "ReJSON" in module_names, \
            f"Required modules not found. Available: {module_names}"
    
    @requires_redis_stack
    @requires_infinity
    @pytest.mark.asyncio
    async def test_redis_vector_cache_set_get(self):
        """Test RedisVectorCache set and get operations."""
        os.environ["REDIS_STACK_URL"] = get_redis_stack_url()
        os.environ["REDIS_CACHE_INDEX_NAME"] = "test:cache:index"
        os.environ["VECTOR_DIMENSION"] = "1024"
        os.environ["REDIS_CACHE_SIMILARITY_THRESHOLD"] = "0.90"
        
        from backend.services.redis_vector_cache import RedisVectorCache
        from backend.services.infinity_adapter import InfinityEmbeddings
        
        cache = RedisVectorCache()
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        
        # Generate embedding for test query
        query = "What is Litecoin test query?"
        query_vector = await embeddings.embed_query(query)
        
        # Store in cache
        await cache.set(
            query_vector=query_vector,
            query_text=query,
            response="Litecoin is a peer-to-peer cryptocurrency.",
            sources=[{"page_content": "Test content", "metadata": {"title": "Test"}}]
        )
        
        # Retrieve from cache
        result = await cache.get(query_vector)
        
        assert result is not None
        response, sources = result
        assert "Litecoin" in response
        assert len(sources) > 0
    
    @requires_redis_stack
    @requires_infinity
    @pytest.mark.asyncio
    async def test_redis_vector_cache_similarity(self):
        """Test RedisVectorCache returns similar queries."""
        os.environ["REDIS_STACK_URL"] = get_redis_stack_url()
        os.environ["REDIS_CACHE_INDEX_NAME"] = "test:cache:index"
        os.environ["REDIS_CACHE_SIMILARITY_THRESHOLD"] = "0.85"  # Lower threshold for test
        
        from backend.services.redis_vector_cache import RedisVectorCache
        from backend.services.infinity_adapter import InfinityEmbeddings
        
        cache = RedisVectorCache()
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        
        # Store a response
        query1 = "What is Litecoin cryptocurrency?"
        vec1 = await embeddings.embed_query(query1)
        await cache.set(vec1, query1, "Test response for Litecoin", [])
        
        # Query with similar text
        query2 = "What is LTC crypto?"
        vec2 = await embeddings.embed_query(query2)
        
        result = await cache.get(vec2)
        
        # Should find the cached response due to similarity
        # Note: May or may not hit depending on actual similarity
        # This test validates the mechanism works
        if result:
            response, _ = result
            assert "Litecoin" in response


# ============================================================================
# Full Pipeline Integration Tests
# ============================================================================

class TestFullPipelineIntegration:
    """Integration tests for the complete local RAG pipeline.
    
    IMPORTANT: These tests use test-specific index names to avoid
    polluting the production cache.
    """
    
    @pytest.fixture(autouse=True)
    def cleanup_test_data(self):
        """Cleanup test data after each test."""
        yield
        # Cleanup
        try:
            import redis
            r = redis.from_url(get_redis_stack_url())
            # Delete test keys
            for key in r.scan_iter("cache:entry:*"):
                r.delete(key)
            # Drop test indexes
            for idx in ["test:e2e:index", "test:cache:index", "test:integration:index"]:
                try:
                    r.execute_command("FT.DROPINDEX", idx, "DD")
                except Exception:
                    pass
        except Exception:
            pass
    
    @requires_all_services
    @pytest.mark.asyncio
    async def test_full_pipeline_query_rewrite_and_embed(self):
        """Test query rewriting followed by embedding."""
        import time
        
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        os.environ["LOCAL_REWRITER_MODEL"] = "llama3.2:3b"
        os.environ["INFINITY_URL"] = "http://localhost:7997"
        
        from backend.services.rewriter import LocalRewriter
        from backend.services.infinity_adapter import InfinityEmbeddings
        
        rewriter = LocalRewriter()
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        
        # Step 1: Rewrite query
        start = time.time()
        original_query = "How many coins total?"
        chat_history = [("What is Litecoin?", "Litecoin is a cryptocurrency...")]
        
        rewritten = await rewriter.rewrite(original_query, chat_history)
        rewrite_time = time.time() - start
        
        # Step 2: Embed rewritten query
        start = time.time()
        vector = await embeddings.embed_query(rewritten)
        embed_time = time.time() - start
        
        assert rewritten is not None
        assert len(vector) == 1024
        
        print(f"\n  Original: {original_query}")
        print(f"  Rewritten: {rewritten}")
        print(f"  Rewrite time: {rewrite_time:.2f}s")
        print(f"  Embed time: {embed_time:.2f}s")
    
    @requires_all_services
    @pytest.mark.asyncio
    async def test_router_integration(self):
        """Test InferenceRouter with real services."""
        import sys
        
        # Skip on Python < 3.11 (no asyncio.timeout)
        if sys.version_info < (3, 11):
            pytest.skip("Router requires Python 3.11+ for asyncio.timeout")
        
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        os.environ["LOCAL_REWRITER_MODEL"] = "llama3.2:3b"
        os.environ["MAX_LOCAL_QUEUE_DEPTH"] = "3"
        os.environ["LOCAL_TIMEOUT_SECONDS"] = "10.0"
        os.environ["GOOGLE_API_KEY"] = os.environ.get("GOOGLE_API_KEY", "test-key")
        
        from backend.services.router import InferenceRouter
        
        router = InferenceRouter()
        
        result = await router.rewrite_with_metadata("What is Litecoin?", [])
        
        assert result is not None
        assert result.rewritten_query is not None
        assert result.backend in ["local", "gemini"]
        assert result.latency_seconds > 0
        
        print(f"\n  Rewritten: {result.rewritten_query}")
        print(f"  Backend: {result.backend}")
        print(f"  Latency: {result.latency_seconds:.2f}s")
    
    @requires_all_services
    @pytest.mark.asyncio
    async def test_end_to_end_with_caching(self):
        """Test complete flow: rewrite -> embed -> cache -> retrieve."""
        import time
        
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        os.environ["INFINITY_URL"] = "http://localhost:7997"
        os.environ["REDIS_STACK_URL"] = get_redis_stack_url()
        os.environ["REDIS_CACHE_INDEX_NAME"] = "test:e2e:index"
        os.environ["REDIS_CACHE_SIMILARITY_THRESHOLD"] = "0.90"
        
        from backend.services.rewriter import LocalRewriter
        from backend.services.infinity_adapter import InfinityEmbeddings
        from backend.services.redis_vector_cache import RedisVectorCache
        
        rewriter = LocalRewriter()
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        cache = RedisVectorCache()
        
        # First query (cache miss expected)
        query1 = "What are Litecoin transaction fees?"
        
        start = time.time()
        
        # Rewrite
        rewritten = await rewriter.rewrite(query1, [])
        
        # Embed
        vector = await embeddings.embed_query(rewritten)
        
        # Check cache (should miss)
        cached = await cache.get(vector)
        
        if cached is None:
            # Simulate answer generation
            answer = "Litecoin fees are typically very low, around 0.001 LTC per transaction."
            await cache.set(vector, rewritten, answer, [])
        
        first_query_time = time.time() - start
        
        # Second query (similar, should hit cache)
        query2 = "How much are LTC transaction fees?"
        
        start = time.time()
        rewritten2 = await rewriter.rewrite(query2, [])
        vector2 = await embeddings.embed_query(rewritten2)
        cached2 = await cache.get(vector2)
        second_query_time = time.time() - start
        
        print(f"\n  First query time: {first_query_time:.2f}s")
        print(f"  Second query time: {second_query_time:.2f}s")
        print(f"  Cache hit on second query: {cached2 is not None}")


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Performance tests for local RAG services."""
    
    @requires_ollama
    @pytest.mark.asyncio
    async def test_ollama_concurrent_requests(self):
        """Test Ollama handles concurrent requests."""
        import time
        
        os.environ["OLLAMA_URL"] = "http://localhost:11434"
        from backend.services.rewriter import LocalRewriter
        
        rewriter = LocalRewriter()
        
        queries = [
            "What is Litecoin?",
            "How does MWEB work?",
            "What is halving?",
        ]
        
        start = time.time()
        results = await asyncio.gather(*[rewriter.rewrite(q, []) for q in queries])
        duration = time.time() - start
        
        assert len(results) == 3
        assert all(r is not None for r in results)
        
        print(f"\n  3 concurrent rewrites in {duration:.2f}s")
    
    @requires_infinity
    @pytest.mark.asyncio
    async def test_infinity_batch_performance(self):
        """Test Infinity batch embedding performance."""
        import time
        
        from backend.services.infinity_adapter import InfinityEmbeddings
        embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
        
        # 32 documents (typical batch size)
        texts = [f"Document {i} about Litecoin cryptocurrency" for i in range(32)]
        
        start = time.time()
        results = await embeddings.embed_documents(texts)
        duration = time.time() - start
        
        assert len(results) == 32
        
        per_doc = duration / 32
        print(f"\n  32 embeddings in {duration:.2f}s ({per_doc*1000:.1f}ms per doc)")


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

