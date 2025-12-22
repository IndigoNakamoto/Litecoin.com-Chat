import os
import logging
from typing import List, Dict, Any, Optional
from pymongo import MongoClient, UpdateOne
import torch
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    # Fallback to deprecated import for backward compatibility
    from langchain_community.embeddings import HuggingFaceEmbeddings
from cache_utils import embedding_cache
import numpy as np

logger = logging.getLogger(__name__)

# Import Google embeddings if available
try:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    GOOGLE_EMBEDDINGS_AVAILABLE = True
except ImportError:
    GOOGLE_EMBEDDINGS_AVAILABLE = False
    logging.getLogger(__name__).warning("langchain_google_genai not available. Google embeddings will not work.")

# Global shared MongoClient instance for connection pool sharing
# This prevents creating multiple connection pools when multiple VectorStoreManager instances are created
_shared_mongo_client: Optional[MongoClient] = None
_shared_mongo_client_lock = None

# Global lock for FAISS index rebuilds to prevent thundering herd problem
# When multiple webhooks trigger simultaneously, only one rebuild should happen
_faiss_rebuild_lock = None
_faiss_rebuild_in_progress = False

def _get_shared_mongo_client() -> Optional[MongoClient]:
    """
    Returns a shared MongoClient instance for connection pool sharing.
    This ensures all VectorStoreManager instances use the same connection pool.
    """
    global _shared_mongo_client, _shared_mongo_client_lock
    
    # Lazy import threading to avoid circular dependencies
    if _shared_mongo_client_lock is None:
        import threading
        _shared_mongo_client_lock = threading.Lock()
    
    if _shared_mongo_client is None:
        mongo_uri = os.getenv("MONGO_URI")
        if mongo_uri:
            try:
                with _shared_mongo_client_lock:
                    # Double-check pattern in case another thread created it
                    if _shared_mongo_client is None:
                        _shared_mongo_client = MongoClient(
                            mongo_uri,
                            serverSelectionTimeoutMS=5000,
                            maxPoolSize=50,
                            minPoolSize=10,
                            maxIdleTimeMS=30000,
                            waitQueueTimeoutMS=5000,
                            retryWrites=True,
                            retryReads=True
                        )
                        _shared_mongo_client.admin.command('ping')
                        logger.info("Shared MongoDB client created with connection pooling")
            except Exception as e:
                logger.warning(f"Failed to create shared MongoDB client: {e}")
                return None
    
    return _shared_mongo_client

def close_shared_mongo_client():
    """
    Closes the shared MongoClient instance.
    Should be called during application shutdown.
    """
    global _shared_mongo_client
    if _shared_mongo_client is not None:
        try:
            _shared_mongo_client.close()
            logger.info("Shared MongoDB client closed")
        except Exception as e:
            logger.error(f"Error closing shared MongoDB client: {e}")
        finally:
            _shared_mongo_client = None

def _get_faiss_rebuild_lock():
    """
    Returns a lock for serializing FAISS index rebuilds.
    Prevents thundering herd when multiple webhooks trigger simultaneously.
    """
    global _faiss_rebuild_lock
    if _faiss_rebuild_lock is None:
        import threading
        _faiss_rebuild_lock = threading.Lock()
    return _faiss_rebuild_lock

def _is_faiss_rebuild_in_progress() -> bool:
    """Check if a FAISS rebuild is currently in progress."""
    global _faiss_rebuild_in_progress
    return _faiss_rebuild_in_progress

def _set_faiss_rebuild_in_progress(value: bool):
    """Set the FAISS rebuild in progress flag."""
    global _faiss_rebuild_in_progress
    _faiss_rebuild_in_progress = value

# Auto-detect Apple M1/M2/M3 GPU (Metal Performance Shaders)
if torch.backends.mps.is_available():
    device = "mps"
    logger.info("Using Apple MPS (M1/M2/M3 GPU) for embeddings.")
elif torch.cuda.is_available():
    device = "cuda"
    logger.info("Using NVIDIA CUDA (GPU) for embeddings.")
else:
    device = "cpu"
    logger.info("GPU not available. Using CPU for embeddings.")

# Default local embedding model - best quality for semantic search (recommended: all-mpnet-base-v2)
# Can be overridden with EMBEDDING_MODEL environment variable
# Google models: gemini-embedding-001, text-embedding-004
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
EMBEDDING_MODEL_KWARGS = {"device": device}
ENCODE_KWARGS = {"normalize_embeddings": True}  # Normalize embeddings for better similarity search

# Google embedding models (detected by model name)
GOOGLE_EMBEDDING_MODELS = {
    "gemini-embedding-001",
    "text-embedding-004",
    "models/gemini-embedding-001",
    "models/text-embedding-004",
}

def is_google_embedding_model(model_name: str) -> bool:
    """Check if the model name is a Google embedding model."""
    # Remove 'models/' prefix if present for comparison
    model_base = model_name.replace("models/", "")
    return model_base in GOOGLE_EMBEDDING_MODELS or model_name.startswith("gemini-") or model_name.startswith("text-embedding-")

def get_embedding_model():
    """
    Helper function to get an embedding model (local or Google).
    Automatically detects if the model is a Google model and uses the appropriate class.
    """
    model_name = DEFAULT_EMBEDDING_MODEL
    
    # Check if this is a Google embedding model
    if is_google_embedding_model(model_name):
        if not GOOGLE_EMBEDDINGS_AVAILABLE:
            logger.warning("langchain_google_genai not available. Google embeddings will not work.")
            raise ImportError(
                f"Google embedding model '{model_name}' requires langchain_google_genai. "
                "Install it with: pip install langchain-google-genai"
            )
        
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise ValueError(
                f"Google embedding model '{model_name}' requires GOOGLE_API_KEY environment variable"
            )
        
        try:
            # Format model name for Google API (add 'models/' prefix if not present)
            if not model_name.startswith("models/"):
                google_model_name = f"models/{model_name}"
            else:
                google_model_name = model_name
            
            # Determine task type based on model
            # gemini-embedding-001 supports task_type parameter
            task_type = "retrieval_document" if "gemini" in model_name.lower() else None
            
            embeddings_kwargs = {
                "model": google_model_name,
                "google_api_key": google_api_key,
            }
            
            if task_type:
                embeddings_kwargs["task_type"] = task_type
            
            embeddings = GoogleGenerativeAIEmbeddings(**embeddings_kwargs)
            logger.info(f"Google embedding model '{google_model_name}' initialized successfully")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to initialize Google embedding model '{model_name}': {e}")
            raise
    
    # Use local HuggingFace embeddings
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=EMBEDDING_MODEL_KWARGS,
            encode_kwargs=ENCODE_KWARGS
        )
        logger.info(f"Local embedding model '{model_name}' initialized successfully")
        return embeddings
    except Exception as e:
        logger.error(f"Failed to initialize local embedding model '{model_name}': {e}")
        raise

# Backward compatibility alias
def get_local_embedding_model():
    """
    Deprecated: Use get_embedding_model() instead.
    This function is kept for backward compatibility.
    """
    return get_embedding_model()


class VectorStoreManager:
    """
    Simplified VectorStoreManager using FAISS with local embeddings.
    Manages interactions with FAISS vector store and optional MongoDB document storage.
    """
    
    def __init__(self, db_name: str = "litecoin_rag_db", collection_name: str = "litecoin_docs"):
        """
        Initializes the VectorStoreManager with local embeddings.

        Args:
            db_name: The name of the database to use.
            collection_name: The name of the collection to use.
        """
        self.mongo_uri = os.getenv("MONGO_URI")
        self.mongodb_available = False
        self.db_name = db_name
        self.collection_name = collection_name
        self.client = None  # Will use shared client, not own instance
        self._owns_client = False  # Track if we own the client (for cleanup)

        # Use shared MongoDB connection pool instead of creating new one
        # This prevents connection pool accumulation when multiple VectorStoreManager instances are created
        if self.mongo_uri:
            try:
                self.client = _get_shared_mongo_client()
                if self.client:
                    self.mongodb_available = True
                    self.collection = self.client[self.db_name][self.collection_name]
                    logger.info(f"MongoDB connection successful using shared connection pool (db: {self.db_name}, collection: {self.collection_name})")
                else:
                    logger.warning("Shared MongoDB client unavailable. Using FAISS only mode.")
                    self.mongodb_available = False
            except Exception as e:
                logger.warning(f"MongoDB connection failed: {e}. Using FAISS only mode.")
                self.mongodb_available = False
        else:
            logger.warning("MONGO_URI not set. Using FAISS only mode.")
            self.mongodb_available = False

        # Check if we should use Infinity embeddings with 1024-dim index
        self.use_infinity = os.getenv("USE_INFINITY_EMBEDDINGS", "false").lower() == "true"
        
        if self.use_infinity:
            # Use 1024-dim index with placeholder embeddings
            # Actual embedding is done by InfinityEmbeddings, FAISS just needs a compatible function
            self.faiss_index_path = os.getenv("FAISS_INDEX_PATH_1024", "./backend/faiss_index_1024")
            logger.info(f"Using Infinity embeddings mode with 1024-dim index: {self.faiss_index_path}")
            
            # Placeholder embeddings for LangChain FAISS compatibility
            # The actual embedding is done externally via InfinityEmbeddings
            class PlaceholderEmbeddings:
                """Placeholder for LangChain FAISS compatibility when using external embeddings."""
                def embed_documents(self, texts): 
                    raise NotImplementedError("Use InfinityEmbeddings.embed_documents() instead")
                def embed_query(self, text):
                    raise NotImplementedError("Use InfinityEmbeddings.embed_query() instead")
            
            self.embeddings = PlaceholderEmbeddings()
        else:
            # Initialize embeddings (local or Google) - legacy mode
            self.embeddings = get_embedding_model()
            self.faiss_index_path = os.getenv("FAISS_INDEX_PATH", "./backend/faiss_index")
        
        # Ensure directory exists
        os.makedirs(self.faiss_index_path, exist_ok=True)

        # Try to load existing FAISS index, otherwise create empty or from MongoDB
        index_file = os.path.join(self.faiss_index_path, "index.faiss")
        if os.path.exists(index_file):
            logger.info(f"Loading existing FAISS index from {self.faiss_index_path}")
            try:
                self.vector_store = FAISS.load_local(
                    self.faiss_index_path, 
                    self.embeddings, 
                    allow_dangerous_deserialization=True
                )
                logger.info("FAISS index loaded successfully")
                
                # Check if FAISS index is stale (empty or suspiciously small compared to MongoDB)
                if self.mongodb_available:
                    faiss_count = self.vector_store.index.ntotal if hasattr(self.vector_store, 'index') and hasattr(self.vector_store.index, 'ntotal') else 0
                    mongo_count = self.collection.count_documents({})
                    
                    # Rebuild if FAISS is empty but MongoDB has documents
                    # Also rebuild if FAISS has very few vectors (< 10) but MongoDB has many documents (> 10)
                    # This handles the case where the index was created from just 1 document but MongoDB now has more
                    if mongo_count > 0:
                        if faiss_count == 0:
                            logger.warning(
                                f"FAISS index is empty but MongoDB has {mongo_count} documents. Rebuilding from MongoDB..."
                            )
                            self.vector_store = self._create_faiss_from_mongodb()
                            logger.info("FAISS index rebuilt from MongoDB")
                        elif faiss_count < 10 and mongo_count > 10:
                            logger.warning(
                                f"FAISS index appears stale: FAISS has {faiss_count} vectors, "
                                f"MongoDB has {mongo_count} documents. Rebuilding from MongoDB..."
                            )
                            self.vector_store = self._create_faiss_from_mongodb()
                            logger.info("FAISS index rebuilt from MongoDB")
                        else:
                            logger.info(f"FAISS index check: {faiss_count} vectors, MongoDB has {mongo_count} documents")
                    else:
                        logger.info(f"FAISS index check: {faiss_count} vectors, MongoDB has {mongo_count} documents")
                        
            except Exception as e:
                logger.warning(f"Failed to load existing FAISS index: {e}. Creating new index.")
                if self.mongodb_available:
                    self.vector_store = self._create_faiss_from_mongodb()
                else:
                    self.vector_store = self._create_empty_faiss_index()
        elif self.mongodb_available:
            logger.info("No existing FAISS index found, creating from MongoDB documents")
            self.vector_store = self._create_faiss_from_mongodb()
        else:
            logger.info("No existing FAISS index and MongoDB unavailable, creating empty FAISS index")
            self.vector_store = self._create_empty_faiss_index()

        logger.info(f"VectorStoreManager initialized (MongoDB: {'available' if self.mongodb_available else 'unavailable'})")

    def _create_empty_faiss_index(self):
        """Creates an empty FAISS index with a placeholder document."""
        if self.use_infinity:
            # For Infinity mode, create index with a placeholder vector
            # The dimension must match the Infinity embedding dimension (1024)
            import numpy as np
            dimension = int(os.getenv("VECTOR_DIMENSION", "1024"))
            placeholder_embedding = [0.0] * dimension
            
            # Use from_embeddings with a placeholder
            vector_store = FAISS.from_embeddings(
                text_embeddings=[("placeholder", placeholder_embedding)],
                embedding=self.embeddings,
                metadatas=[{"placeholder": True}]
            )
            vector_store.save_local(self.faiss_index_path)
            logger.info(f"Created empty FAISS index (Infinity mode, {dimension}-dim) at {self.faiss_index_path}")
            return vector_store
        else:
            # Legacy mode: use from_texts with a non-empty placeholder
            # Google embeddings and others don't accept empty text
            placeholder_text = "This is a placeholder document for initializing the FAISS index."
            vector_store = FAISS.from_texts(
                [placeholder_text], 
                self.embeddings,
                metadatas=[{"placeholder": True}]
            )
            vector_store.save_local(self.faiss_index_path)
            logger.info(f"Created empty FAISS index at {self.faiss_index_path}")
            return vector_store

    def _create_faiss_from_mongodb(self):
        """
        Creates FAISS vector store from existing MongoDB documents.
        
        Uses a global lock to prevent thundering herd when multiple webhooks
        trigger simultaneously (e.g., bulk status changes in CMS).
        """
        if not self.mongodb_available:
            return self._create_empty_faiss_index()
        
        # Acquire lock to serialize FAISS rebuilds
        rebuild_lock = _get_faiss_rebuild_lock()
        
        # Try to acquire the lock - if another rebuild is in progress, skip this one
        acquired = rebuild_lock.acquire(blocking=False)
        if not acquired:
            logger.info("FAISS rebuild already in progress, skipping duplicate rebuild request")
            # Return existing index if available, otherwise wait for lock
            index_file = os.path.join(self.faiss_index_path, "index.faiss")
            if os.path.exists(index_file):
                try:
                    return FAISS.load_local(
                        self.faiss_index_path, 
                        self.embeddings, 
                        allow_dangerous_deserialization=True
                    )
                except Exception:
                    pass
            # If no existing index, we need to wait for the rebuild
            rebuild_lock.acquire(blocking=True)
        
        _set_faiss_rebuild_in_progress(True)
        logger.info("Acquired FAISS rebuild lock, starting index rebuild...")
        
        try:
            # Load all documents from MongoDB.
            # If embeddings are present, rebuild FAISS from stored embeddings (no re-embed).
            # If embeddings are missing, optionally backfill them (guarded by env var).
            mongo_docs = list(self.collection.find({}))

            texts: List[str] = []
            metadatas: List[Dict[str, Any]] = []
            embeddings: List[List[float]] = []
            missing_for_backfill: List[Dict[str, Any]] = []

            for doc in mongo_docs:
                text = doc.get("text", "") or ""
                if not text:
                    continue
                metadata = doc.get("metadata", {}) or {}
                emb = doc.get("embedding")
                if isinstance(emb, list) and emb:
                    texts.append(text)
                    metadatas.append(metadata)
                    embeddings.append(emb)
                else:
                    missing_for_backfill.append(
                        {
                            "_id": doc.get("_id"),
                            "text": text,
                            "metadata": metadata,
                        }
                    )

            if not texts and not missing_for_backfill:
                logger.info("No documents in MongoDB, creating empty FAISS index")
                return self._create_empty_faiss_index()

            # Backfill missing embeddings if needed.
            # If allow_backfill is false, we will still embed missing docs for this rebuild,
            # but we won't persist them to MongoDB (so operators can choose to run backfill explicitly).
            if missing_for_backfill:
                allow_backfill = os.getenv("ALLOW_EMBEDDING_BACKFILL_ON_REBUILD", "false").lower() == "true"
                backfill_batch_size = int(os.getenv("EMBEDDING_BACKFILL_BATCH_SIZE", "10"))

                if allow_backfill:
                    logger.info(
                        "Backfilling %s MongoDB docs missing embeddings during rebuild (ALLOW_EMBEDDING_BACKFILL_ON_REBUILD=true)",
                        len(missing_for_backfill),
                    )
                else:
                    logger.warning(
                        "Found %s MongoDB docs missing embeddings. "
                        "Rebuild will embed them now, but will NOT persist. "
                        "Set ALLOW_EMBEDDING_BACKFILL_ON_REBUILD=true or run a dedicated backfill script.",
                        len(missing_for_backfill),
                    )

                updates: List[UpdateOne] = []

                if self.use_infinity:
                    import httpx

                    infinity_url = os.getenv("INFINITY_URL", "http://localhost:7997")
                    model_id = os.getenv("EMBEDDING_MODEL_ID", "BAAI/bge-m3")

                    with httpx.Client(timeout=120.0) as client:
                        for i in range(0, len(missing_for_backfill), backfill_batch_size):
                            batch_missing = missing_for_backfill[i : i + backfill_batch_size]
                            batch_texts = [d["text"] for d in batch_missing]

                            batch_num = i // backfill_batch_size + 1
                            total_batches = (len(missing_for_backfill) + backfill_batch_size - 1) // backfill_batch_size
                            logger.info(f"Embedding backfill batch {batch_num}/{total_batches} from MongoDB...")

                            response = client.post(
                                f"{infinity_url}/embeddings",
                                json={
                                    "input": batch_texts,
                                    "model": model_id,
                                    "encoding_format": "float",
                                },
                            )
                            response.raise_for_status()
                            result = response.json()
                            batch_embeddings = [item["embedding"] for item in result.get("data", [])]

                            if len(batch_embeddings) != len(batch_texts):
                                raise ValueError(
                                    f"Backfill embedding count mismatch: got {len(batch_embeddings)}, expected {len(batch_texts)}"
                                )

                            embedding_dim = len(batch_embeddings[0]) if batch_embeddings else 0
                            for doc_row, emb in zip(batch_missing, batch_embeddings):
                                md = dict(doc_row.get("metadata") or {})
                                md.setdefault("embedding_model", model_id)
                                if embedding_dim:
                                    md.setdefault("embedding_dim", embedding_dim)

                                texts.append(doc_row["text"])
                                metadatas.append(md)
                                embeddings.append(emb)

                                if allow_backfill and doc_row.get("_id") is not None:
                                    updates.append(
                                        UpdateOne(
                                            {"_id": doc_row["_id"]},
                                            {"$set": {"embedding": emb, "metadata": md}},
                                        )
                                    )
                else:
                    embedding_model = DEFAULT_EMBEDDING_MODEL

                    for i in range(0, len(missing_for_backfill), backfill_batch_size):
                        batch_missing = missing_for_backfill[i : i + backfill_batch_size]
                        batch_texts = [d["text"] for d in batch_missing]

                        batch_num = i // backfill_batch_size + 1
                        total_batches = (len(missing_for_backfill) + backfill_batch_size - 1) // backfill_batch_size
                        logger.info(f"Embedding backfill batch {batch_num}/{total_batches} from MongoDB...")

                        batch_embeddings = self.get_cached_embeddings(batch_texts)
                        embedding_dim = len(batch_embeddings[0]) if batch_embeddings else 0

                        for doc_row, emb in zip(batch_missing, batch_embeddings):
                            md = dict(doc_row.get("metadata") or {})
                            md.setdefault("embedding_model", embedding_model)
                            if embedding_dim:
                                md.setdefault("embedding_dim", embedding_dim)

                            texts.append(doc_row["text"])
                            metadatas.append(md)
                            embeddings.append(emb)

                            if allow_backfill and doc_row.get("_id") is not None:
                                updates.append(
                                    UpdateOne(
                                        {"_id": doc_row["_id"]},
                                        {"$set": {"embedding": emb, "metadata": md}},
                                    )
                                )

                if allow_backfill and updates:
                    try:
                        self.collection.bulk_write(updates, ordered=False)
                        logger.info("Backfill persisted %s embeddings to MongoDB", len(updates))
                    except Exception as e:
                        logger.warning("Failed to persist backfilled embeddings to MongoDB: %s", e, exc_info=True)

            if not texts:
                logger.info("No documents available for FAISS rebuild after filtering; creating empty FAISS index")
                return self._create_empty_faiss_index()

            logger.info(f"Creating FAISS index from {len(texts)} documents in MongoDB (stored embeddings)")

            # Create FAISS from stored embeddings (works for both Infinity + legacy)
            text_embeddings = list(zip(texts, embeddings))
            vector_store = FAISS.from_embeddings(
                text_embeddings=text_embeddings,
                embedding=self.embeddings,
                metadatas=metadatas,
            )
            vector_store.save_local(self.faiss_index_path)
            logger.info(f"FAISS index created from stored embeddings and saved to {self.faiss_index_path}")
            return vector_store
        finally:
            # Always release the lock
            _set_faiss_rebuild_in_progress(False)
            rebuild_lock.release()
            logger.info("Released FAISS rebuild lock")

    def _save_faiss_index(self):
        """Saves the current FAISS index to disk."""
        try:
            self.vector_store.save_local(self.faiss_index_path)
            logger.info(f"FAISS index saved to {self.faiss_index_path}")
        except Exception as e:
            logger.error(f"Error saving FAISS index: {e}")

    def reload_from_disk(self):
        """
        Reloads the FAISS index from disk without rebuilding from MongoDB.
        
        This is a fast operation that should be used after add_documents() 
        when you want other components to see the new content.
        
        Returns:
            True if reload succeeded, False otherwise
        """
        index_file = os.path.join(self.faiss_index_path, "index.faiss")
        if not os.path.exists(index_file):
            logger.warning(f"FAISS index file not found at {index_file}, cannot reload")
            return False
        
        try:
            self.vector_store = FAISS.load_local(
                self.faiss_index_path, 
                self.embeddings, 
                allow_dangerous_deserialization=True
            )
            faiss_count = self.vector_store.index.ntotal if hasattr(self.vector_store, 'index') and hasattr(self.vector_store.index, 'ntotal') else 0
            logger.info(f"FAISS index reloaded from disk ({faiss_count} vectors)")
            return True
        except Exception as e:
            logger.error(f"Error reloading FAISS index from disk: {e}")
            return False

    def add_documents(self, documents: List[Document], batch_size: int = 5):
        """
        Adds documents to FAISS vector store and MongoDB storage in batches.

        Args:
            documents: A list of Langchain Document objects.
            batch_size: The number of documents to process in each batch.
        """
        if not documents:
            logger.info("No documents provided to add.")
            return

        # For Infinity embeddings mode, use sync wrapper for async method
        if self.use_infinity:
            self._add_documents_with_infinity_sync(documents, batch_size)
            return

        # Legacy mode: compute embeddings once and add via add_embeddings (avoid double-embedding)
        total_docs = len(documents)
        success_count = 0
        
        for i in range(0, total_docs, batch_size):
            batch = documents[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(total_docs + batch_size - 1)//batch_size}...")
            try:
                texts = [doc.page_content for doc in batch]
                metadatas = [dict(doc.metadata or {}) for doc in batch]

                # Compute embeddings (cached where possible)
                embeddings = self.get_cached_embeddings(texts)
                embedding_dim = len(embeddings[0]) if embeddings else 0
                embedding_model = DEFAULT_EMBEDDING_MODEL

                # Stamp embedding identity into metadata (helps detect model/dim drift later)
                for md in metadatas:
                    md.setdefault("embedding_model", embedding_model)
                    if embedding_dim:
                        md.setdefault("embedding_dim", embedding_dim)

                # Add to FAISS using precomputed vectors
                text_embeddings = list(zip(texts, embeddings))
                self.vector_store.add_embeddings(text_embeddings, metadatas=metadatas)

                # Store in MongoDB if available (persist embeddings for cheap rebuilds)
                if self.mongodb_available:
                    mongo_docs = []
                    for text, metadata, emb in zip(texts, metadatas, embeddings):
                        mongo_docs.append(
                            {
                                "text": text,
                                "metadata": metadata,
                                "embedding": emb,
                            }
                        )
                    if mongo_docs:
                        self.collection.insert_many(mongo_docs, ordered=False)

                success_count += len(batch)
                logger.info(f"Successfully added batch of {len(batch)} documents.")
            except Exception as e:
                logger.error(f"Error adding batch {i//batch_size + 1}: {e}", exc_info=True)
                raise e

        # Save FAISS index after all additions
        self._save_faiss_index()
        if self.mongodb_available:
            logger.info(f"Finished adding {success_count} of {total_docs} documents to FAISS and MongoDB collection '{self.collection_name}'.")
        else:
            logger.info(f"Finished adding {success_count} of {total_docs} documents to FAISS (MongoDB not available).")
    
    def _add_documents_with_infinity_sync(self, documents: List[Document], batch_size: int = 5):
        """
        Synchronous wrapper for adding documents with Infinity embeddings.
        
        Uses httpx sync client to compute embeddings and adds them to FAISS.
        """
        import httpx
        
        infinity_url = os.getenv("INFINITY_URL", "http://localhost:7997")
        model_id = os.getenv("EMBEDDING_MODEL_ID", "BAAI/bge-m3")
        
        total_docs = len(documents)
        success_count = 0
        
        with httpx.Client(timeout=120.0) as client:
            for i in range(0, total_docs, batch_size):
                batch = documents[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (total_docs + batch_size - 1) // batch_size
                logger.info(f"Processing batch {batch_num}/{total_batches} with Infinity embeddings...")
                
                try:
                    # Get texts and metadatas from batch
                    texts = [doc.page_content for doc in batch]
                    metadatas = [doc.metadata for doc in batch]
                    
                    # Compute embeddings via Infinity service (sync request) with retry
                    max_retries = 3
                    retry_delay = 2.0  # seconds
                    result = None
                    
                    for attempt in range(max_retries):
                        try:
                            response = client.post(
                                f"{infinity_url}/embeddings",
                                json={
                                    "input": texts,
                                    "model": model_id,
                                    "encoding_format": "float"
                                }
                            )
                            response.raise_for_status()
                            result = response.json()
                            break  # Success, exit retry loop
                        except Exception as retry_error:
                            if attempt < max_retries - 1:
                                logger.warning(f"Embedding request failed (attempt {attempt + 1}/{max_retries}): {retry_error}")
                                import time
                                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                            else:
                                raise  # Re-raise on final attempt
                    
                    if result is None:
                        raise ValueError("Failed to get embeddings after retries")
                    
                    # Extract dense embeddings
                    dense_embeddings = [item["embedding"] for item in result.get("data", [])]
                    
                    if len(dense_embeddings) != len(texts):
                        raise ValueError(f"Embedding count mismatch: got {len(dense_embeddings)}, expected {len(texts)}")
                    
                    # Create text-embedding pairs for FAISS
                    text_embeddings = list(zip(texts, dense_embeddings))
                    
                    # Add to FAISS using add_embeddings (works with pre-computed vectors)
                    self.vector_store.add_embeddings(text_embeddings, metadatas=metadatas)
                    
                    # Store in MongoDB if available
                    if self.mongodb_available:
                        embedding_dim = len(dense_embeddings[0]) if dense_embeddings else 0

                        mongo_docs = []
                        for text, metadata, emb in zip(texts, metadatas, dense_embeddings):
                            md = dict(metadata or {})
                            md.setdefault("embedding_model", model_id)
                            if embedding_dim:
                                md.setdefault("embedding_dim", embedding_dim)
                            mongo_docs.append(
                                {
                                    "text": text,
                                    "metadata": md,
                                    "embedding": emb,
                                }
                            )
                        if mongo_docs:
                            self.collection.insert_many(mongo_docs, ordered=False)
                    
                    success_count += len(batch)
                    logger.info(f"Successfully added batch of {len(batch)} documents with Infinity embeddings.")
                    
                except Exception as e:
                    logger.error(f"Error adding batch {batch_num} with Infinity: {e}", exc_info=True)
                    raise e
        
        # Save FAISS index after all additions
        self._save_faiss_index()
        if self.mongodb_available:
            logger.info(f"Finished adding {success_count} of {total_docs} documents to FAISS and MongoDB (Infinity mode).")
        else:
            logger.info(f"Finished adding {success_count} of {total_docs} documents to FAISS (Infinity mode, MongoDB not available).")

    def get_cached_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings for texts with caching to reduce computation.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        cached_embeddings = []
        uncached_texts = []
        uncached_indices = []

        # Check cache for each text
        for i, text in enumerate(texts):
            cached = embedding_cache.get_similar(text)
            if cached is not None:
                cached_embeddings.append(cached.tolist())
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Generate embeddings for uncached texts using local model
        if uncached_texts:
            logger.info(f"Generating embeddings for {len(uncached_texts)} uncached texts using local model")
            new_embeddings = self.embeddings.embed_documents(uncached_texts)

            # Cache the new embeddings
            for text, embedding in zip(uncached_texts, new_embeddings):
                embedding_cache.set(text, np.array(embedding))

            # Insert new embeddings into results
            for i, (idx, embedding) in enumerate(zip(uncached_indices, new_embeddings)):
                cached_embeddings.insert(idx, embedding)

        return cached_embeddings

    def get_retriever(self, search_type="similarity", search_kwargs=None):
        """
        Returns a retriever instance from the vector store.

        Args:
            search_type: The type of search (e.g., "similarity", "mmr").
            search_kwargs: Dictionary of arguments for the retriever (e.g., {"k": 5}).
        """
        if search_kwargs is None:
            search_kwargs = {"k": 10}
        return self.vector_store.as_retriever(
            search_type=search_type,
            search_kwargs=search_kwargs
        )

    def delete_documents_by_metadata_field(self, field_name: str, field_value: Any, rebuild_faiss: bool = False):
        """
        Deletes documents from MongoDB. Optionally rebuilds FAISS index.
        
        By default, this does NOT rebuild FAISS - the caller should handle FAISS updates
        (e.g., by calling add_documents which saves incrementally, then refresh_vector_store
        which reloads from disk).
        
        This is the generic method for deleting documents based on a metadata key-value pair.

        Args:
            field_name: The name of the metadata field to filter on (e.g., "payload_id", "source").
            field_value: The value of the metadata field to match.
            rebuild_faiss: If True, rebuild FAISS index after deletion. Default False for performance.
        """
        if not field_name or field_value is None:
            logger.warning("Field name and value must be provided for deletion.")
            return 0

        if not self.mongodb_available:
            logger.warning("MongoDB not available. Cannot perform selective deletion. Use clear_all_documents to reset FAISS index.")
            return 0

        mongo_filter = {f"metadata.{field_name}": field_value}

        logger.info(f"Attempting to delete documents with filter: {mongo_filter}")
        try:
            result = self.collection.delete_many(mongo_filter)
            logger.info(f"Deleted {result.deleted_count} documents matching filter: {mongo_filter}")

            # Only rebuild FAISS if explicitly requested (expensive operation!)
            if rebuild_faiss:
                logger.info("Rebuilding FAISS index after deletion (rebuild_faiss=True)...")
                self.vector_store = self._create_faiss_from_mongodb()
            else:
                logger.info("Skipping FAISS rebuild (will be updated on next add/refresh)")

            return result.deleted_count
        except Exception as e:
            logger.error(f"An error occurred during deletion with filter {mongo_filter}: {e}", exc_info=True)
            return 0

    def clean_draft_documents(self, rebuild_faiss: bool = True):
        """
        Removes all documents with status != 'published' from both MongoDB and FAISS index.
        This is useful for cleaning up draft content that might still be indexed.
        
        Args:
            rebuild_faiss: If True (default), rebuild FAISS index after cleanup.
        """
        if not self.mongodb_available:
            logger.warning("MongoDB not available. Cannot clean draft documents.")
            return 0

        try:
            logger.info("🧹 Starting cleanup of draft/unpublished documents...")

            # Find documents that are not published (draft, etc.)
            draft_filter = {"metadata.status": {"$ne": "published"}}
            draft_docs_cursor = self.collection.find(draft_filter)
            draft_payload_ids = []

            # Collect payload IDs to delete from FAISS (FAISS doesn't support metadata queries)
            for doc in draft_docs_cursor:
                payload_id = doc.get("metadata", {}).get("payload_id")
                if payload_id:
                    draft_payload_ids.append(payload_id)

            # Delete draft documents from MongoDB
            result = self.collection.delete_many(draft_filter)
            logger.info(f"🗑️ Deleted {result.deleted_count} draft documents from MongoDB")

            # If we have payload IDs, also clean any chunks that might use different status values
            additional_deleted = 0
            if draft_payload_ids:
                additional_filter = {"metadata.payload_id": {"$in": draft_payload_ids}}
                additional_result = self.collection.delete_many(additional_filter)
                additional_deleted = additional_result.deleted_count
                if additional_deleted > 0:
                    logger.info(f"🗑️ Deleted {additional_deleted} additional chunks by payload_id")

            # Only rebuild FAISS if requested
            if rebuild_faiss:
                self.vector_store = self._create_faiss_from_mongodb()
                logger.info("✅ FAISS index rebuilt after draft cleanup")
            else:
                logger.info("✅ Draft cleanup complete (FAISS rebuild skipped)")

            total_deleted = result.deleted_count + additional_deleted
            return total_deleted

        except Exception as e:
            logger.error(f"An error occurred during draft document cleanup: {e}", exc_info=True)
            return 0

    def clear_all_documents(self):
        """
        Deletes all documents from MongoDB and creates empty FAISS index. Use with caution.
        """
        if self.mongodb_available:
            logger.warning(f"Attempting to delete ALL documents from collection: '{self.collection_name}' in db: '{self.db_name}'")
            try:
                result = self.collection.delete_many({})
                logger.info(f"Deleted {result.deleted_count} documents. Collection should now be empty.")
            except Exception as e:
                logger.error(f"An error occurred during clearing all documents: {e}", exc_info=True)
                return 0
        else:
            logger.warning("MongoDB not available. Clearing FAISS index only.")

        # Create empty FAISS index
        self.vector_store = self._create_empty_faiss_index()
        logger.info("FAISS index cleared and saved.")

        return 0 if not self.mongodb_available else result.deleted_count

    def close(self):
        """
        Closes MongoDB connection if this instance owns it.
        Note: With shared connection pool, this is a no-op as the shared client
        should be closed via close_shared_mongo_client() during application shutdown.
        """
        if self._owns_client and self.client:
            try:
                self.client.close()
                logger.info("VectorStoreManager MongoDB client closed")
            except Exception as e:
                logger.error(f"Error closing VectorStoreManager MongoDB client: {e}")
            finally:
                self.client = None
                self.mongodb_available = False


# For direct execution and testing of this module (optional)
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

    logger.info("Testing VectorStoreManager with local embeddings...")
    try:
        manager = VectorStoreManager(collection_name="test_collection")
        
        manager.clear_all_documents()

        doc1 = Document(page_content="This is test document one about apples.", metadata={"source": "test_file_1.txt", "id": 1})
        doc2 = Document(page_content="This is test document two about oranges.", metadata={"source": "test_file_2.txt", "id": 2})
        doc3 = Document(page_content="Another test document, also about apples and fruits.", metadata={"source": "test_file_1.txt", "id": 3})
        
        docs_to_add = [doc1, doc2, doc3]

        logger.info(f"\nAdding {len(docs_to_add)} documents...")
        manager.add_documents(docs_to_add)

        logger.info("\nTesting retrieval for 'apples'...")
        retriever = manager.get_retriever(search_kwargs={"k": 2})
        retrieved_docs = retriever.get_relevant_documents("apples")
        logger.info(f"Retrieved {len(retrieved_docs)} documents for 'apples':")
        for i, doc in enumerate(retrieved_docs):
            logger.info(f"  Doc {i+1}: {doc.page_content[:50]}... (Metadata: {doc.metadata})")
        
        logger.info("\nTesting deletion for metadata field 'source' with value 'test_file_1.txt'...")
        deleted_count = manager.delete_documents_by_metadata_field("source", "test_file_1.txt")
        logger.info(f"Deleted {deleted_count} documents.")

        logger.info("\nTesting retrieval for 'apples' after deletion...")
        retriever_after_delete = manager.get_retriever(search_kwargs={"k": 2})
        retrieved_docs_after_delete = retriever_after_delete.get_relevant_documents("apples")
        logger.info(f"Retrieved {len(retrieved_docs_after_delete)} documents for 'apples' after deletion:")
        for i, doc in enumerate(retrieved_docs_after_delete):
            logger.info(f"  Doc {i+1}: {doc.page_content[:50]}... (Metadata: {doc.metadata})")
            if doc.metadata.get("source") == "test_file_1.txt":
                logger.warning(f"  ⚠️ Found document that should have been deleted!")

        logger.info("\nCleaning up: Deleting all documents from test_collection...")
        manager.clear_all_documents()
        logger.info("\nVectorStoreManager test finished.")

    except Exception as e:
        logger.error(f"An error occurred during VectorStoreManager test: {e}")
        import traceback
        traceback.print_exc()
