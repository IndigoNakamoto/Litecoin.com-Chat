"""
Infinity Embedding Adapter

Provides local embeddings via the Infinity HTTP service using the 
stella_en_1.5B_v5 model (1024-dimensional vectors).

This adapter implements a LangChain-compatible interface for seamless
integration with the existing RAG pipeline.

Usage:
    # Default (uses INFINITY_URL env var)
    embeddings = InfinityEmbeddings()
    
    # Override URL (useful for scripts running from host)
    embeddings = InfinityEmbeddings(infinity_url="http://localhost:7997")
    
    # Embed a single query
    vector = await embeddings.embed_query("What is Litecoin?")
    
    # Embed multiple documents
    vectors = await embeddings.embed_documents(["doc1", "doc2"])
"""

import os
import logging
from typing import List, Optional, Dict, Tuple
import httpx
import numpy as np

logger = logging.getLogger(__name__)


class InfinityEmbeddings:
    """
    Embedding adapter for the Infinity service.
    
    Provides 1024-dimensional embeddings using BGE-M3 model (or configured model).
    Compatible with LangChain's embedding interface.
    
    Attributes:
        infinity_url: URL of the Infinity service
        model_id: Embedding model ID (default: BAAI/bge-m3)
        timeout: Request timeout in seconds
        dimension: Vector dimension (1024 for BGE-M3)
    """
    
    def __init__(
        self,
        infinity_url: Optional[str] = None,
        model_id: Optional[str] = None,
        timeout: float = 120.0,  # Increased from 30s for BGE-M3 batch processing
    ):
        """
        Initialize Infinity embeddings client.
        
        Args:
            infinity_url: Optional override for Infinity service URL.
                         If None, uses INFINITY_URL env var or defaults to localhost.
                         Use 'http://localhost:7997' when running from host,
                         or 'http://infinity:7997' when running from Docker.
            model_id: Optional override for embedding model ID.
                     Defaults to EMBEDDING_MODEL_ID env var or 'BAAI/bge-m3'.
            timeout: Request timeout in seconds (default: 120.0)
        """
        self.infinity_url = infinity_url or os.getenv("INFINITY_URL", "http://localhost:7997")
        self.model_id = model_id or os.getenv("EMBEDDING_MODEL_ID", "BAAI/bge-m3")
        self.timeout = timeout
        self.dimension = int(os.getenv("VECTOR_DIMENSION", "1024"))
        
        logger.info(f"InfinityEmbeddings initialized: url={self.infinity_url}, model={self.model_id}")
    
    async def embed_query(self, text: str) -> Tuple[List[float], Optional[Dict[str, float]]]:
        """
        Embed a single query text with both dense and sparse embeddings.
        
        Args:
            text: The text to embed
            
        Returns:
            Tuple of (dense_embedding, sparse_embedding)
            - dense_embedding: List of floats (1024-dim)
            - sparse_embedding: Dict of {word: weight} or None
            
        Raises:
            httpx.HTTPError: If the request fails
            ValueError: If the response format is invalid
        """
        dense, sparse = await self.embed_documents([text])
        return dense[0], sparse[0] if sparse else None
    
    async def embed_query_dense(self, text: str) -> List[float]:
        """
        Embed a single query text (dense only, for backward compatibility).
        
        Args:
            text: The text to embed
            
        Returns:
            List of floats representing the dense embedding vector (1024-dim)
        """
        dense, _ = await self.embed_query(text)
        return dense
    
    @staticmethod
    def sparse_similarity(query_sparse: Dict[str, float], doc_sparse: Dict[str, float]) -> float:
        """
        Compute cosine similarity between two sparse embeddings.
        
        Args:
            query_sparse: Query sparse embedding {word: weight}
            doc_sparse: Document sparse embedding {word: weight}
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not query_sparse or not doc_sparse:
            return 0.0
        
        # Compute dot product and norms
        dot_product = sum(query_sparse.get(word, 0) * doc_sparse.get(word, 0) 
                         for word in set(query_sparse.keys()) | set(doc_sparse.keys()))
        
        query_norm = sum(w * w for w in query_sparse.values()) ** 0.5
        doc_norm = sum(w * w for w in doc_sparse.values()) ** 0.5
        
        if query_norm == 0 or doc_norm == 0:
            return 0.0
        
        return dot_product / (query_norm * doc_norm)
    
    async def embed_documents(self, texts: List[str]) -> Tuple[List[List[float]], List[Optional[Dict[str, float]]]]:
        """
        Embed multiple documents.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            Tuple of (dense_embeddings, sparse_embeddings)
            - dense_embeddings: List of embedding vectors (each 1024-dim)
            - sparse_embeddings: List of sparse embeddings (dicts or None)
            
        Raises:
            httpx.HTTPError: If the request fails
            ValueError: If the response format is invalid
        """
        if not texts:
            return []

        from backend.services.circuit_breaker import CircuitOpen, infinity_breaker

        async def _do():
            return await self._embed_documents_inner(texts)

        try:
            return await infinity_breaker.call(_do)
        except CircuitOpen as e:
            raise httpx.ConnectError(str(e)) from e

    async def _embed_documents_inner(self, texts: List[str]) -> Tuple[List[List[float]], List[Optional[Dict[str, float]]]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.infinity_url}/embeddings",
                    json={
                        "model": self.model_id,
                        "input": texts,
                        "encoding_format": "float",  # Ensure consistent format with document embeddings
                    },
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Extract embeddings from OpenAI-compatible response format
                # Response format: {"data": [{"embedding": [...], "index": 0}, ...]}
                if "data" not in data:
                    raise ValueError(f"Invalid response format: missing 'data' key. Response: {data}")
                
                # Sort by index to ensure correct order
                sorted_data = sorted(data["data"], key=lambda x: x.get("index", 0))
                dense_embeddings = [item["embedding"] for item in sorted_data]
                sparse_embeddings = [item.get("sparse_embedding") for item in sorted_data]
                
                # Validate embedding dimensions
                if dense_embeddings:
                    actual_dim = len(dense_embeddings[0])
                    expected_dim = self.dimension
                    if actual_dim != expected_dim:
                        logger.warning(
                            f"Embedding dimension mismatch: got {actual_dim}, expected {expected_dim}. "
                            f"This may cause search issues!"
                        )
                    # Validate all embeddings have same dimension
                    for i, emb in enumerate(dense_embeddings):
                        if len(emb) != actual_dim:
                            raise ValueError(
                                f"Embedding {i} has inconsistent dimension: {len(emb)} vs {actual_dim}"
                            )
                
                logger.debug(f"Generated {len(dense_embeddings)} embeddings (dim={len(dense_embeddings[0]) if dense_embeddings else 0})")
                logger.debug(f"Sparse embeddings available: {sum(1 for s in sparse_embeddings if s is not None)}/{len(sparse_embeddings)}")
                return dense_embeddings, sparse_embeddings
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Infinity API error: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Infinity connection error: {e}")
                raise
    
    def embed_query_sync(self, text: str) -> List[float]:
        """
        Synchronous version of embed_query for compatibility with LangChain.
        Returns only dense embedding (backward compatible).
        
        Args:
            text: The text to embed
            
        Returns:
            List of floats representing the dense embedding vector
        """
        import asyncio
        
        # Get or create event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            # We're in an async context, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.embed_query_dense(text))
                return future.result()
        else:
            return asyncio.run(self.embed_query_dense(text))
    
    def embed_documents_sync(self, texts: List[str]) -> List[List[float]]:
        """
        Synchronous version of embed_documents for compatibility with LangChain.
        Returns only dense embeddings (backward compatible).
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of dense embedding vectors
        """
        import asyncio
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.embed_documents(texts))
                dense, _ = future.result()  # Extract only dense embeddings
                return dense
        else:
            dense, _ = asyncio.run(self.embed_documents(texts))
            return dense
    
    async def health_check(self) -> bool:
        """
        Check if the Infinity service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        from backend.services.circuit_breaker import CircuitOpen, infinity_breaker

        async def _do() -> bool:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.infinity_url}/health")
                return response.status_code == 200

        try:
            return await infinity_breaker.call(_do)
        except CircuitOpen:
            return False
        except Exception as e:
            logger.warning(f"Infinity health check failed: {e}")
            return False


class InfinityEmbeddingsLangChain:
    """
    LangChain-compatible wrapper for InfinityEmbeddings.
    
    This class provides the exact interface expected by LangChain's
    Embeddings base class, including synchronous methods.
    """
    
    def __init__(self, infinity_url: Optional[str] = None, model_id: Optional[str] = None):
        """Initialize with optional URL and model override."""
        self._infinity = InfinityEmbeddings(infinity_url=infinity_url, model_id=model_id)
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query (synchronous)."""
        return self._infinity.embed_query_sync(text)
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents (synchronous)."""
        return self._infinity.embed_documents_sync(texts)
    
    async def aembed_query(self, text: str) -> List[float]:
        """Embed a single query (async)."""
        return await self._infinity.embed_query(text)
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents (async)."""
        return await self._infinity.embed_documents(texts)

