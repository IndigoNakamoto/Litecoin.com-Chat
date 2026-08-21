from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
import logging
from pydantic import ValidationError
from datetime import datetime
from typing import Dict, Any, List, Union
import os
import json

from backend.data_models import PayloadWebhookDoc
from backend.data_ingestion.embedding_processor import process_payload_documents, process_payload_documents_with_faq
from backend.data_ingestion.vector_store_manager import VectorStoreManager
from backend.rag_pipeline import RAGPipeline
from backend.utils.webhook_auth import verify_webhook_request
import asyncio

# Global RAG pipeline instance reference (set by main.py to avoid circular imports)
# This prevents creating new connection pools per webhook request
_global_rag_pipeline = None

def set_global_rag_pipeline(rag_pipeline):
    """
    Set the global RAG pipeline instance.
    Called by main.py during application startup to avoid circular imports.
    """
    global _global_rag_pipeline
    _global_rag_pipeline = rag_pipeline
    logger.info("Global RAG pipeline instance set for payload sync endpoints")

# Import monitoring metrics
try:
    from backend.monitoring.metrics import (
        webhook_processing_total,
        webhook_processing_duration_seconds,
    )
    MONITORING_ENABLED = True
except ImportError:
    MONITORING_ENABLED = False

router = APIRouter()
logger = logging.getLogger(__name__)

def normalize_relationship_fields(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize relationship fields that may come as objects or strings from Payload CMS.
    This handles differences between create/update hooks and delete hooks.
    """
    normalized = doc_data.copy()

    # Handle author field - can be string ID or full user object
    if 'author' in normalized:
        author = normalized['author']
        if isinstance(author, dict) and 'id' in author:
            normalized['author'] = author['id']
        elif isinstance(author, str):
            # Already a string, keep as is
            pass
        else:
            # If it's neither, set to None to avoid validation errors
            logger.warning(f"Unexpected author format: {type(author)}, setting to None")
            normalized['author'] = None

    # Handle category field - can be list of string IDs or list of objects
    if 'category' in normalized:
        category = normalized['category']
        if isinstance(category, list):
            normalized_category = []
            for cat in category:
                if isinstance(cat, str):
                    normalized_category.append(cat)
                elif isinstance(cat, dict) and 'id' in cat:
                    normalized_category.append(cat['id'])
                else:
                    logger.warning(f"Unexpected category item format: {type(cat)}, skipping")
            normalized['category'] = normalized_category
        else:
            # If not a list, set to empty list
            logger.warning(f"Category field is not a list: {type(category)}, setting to empty list")
            normalized['category'] = []

    return normalized

def delete_and_refresh_vector_store(payload_id, operation="delete"):
    """
    Background task to delete documents by payload_id and refresh the RAG pipeline.
    
    Args:
        payload_id: The Payload CMS document ID
        operation: The operation type ("delete" or "unpublish")
    """
    start_time = datetime.utcnow()
    
    try:
        logger.info(f"🗑️ [Delete Task: {payload_id}] Starting deletion and refresh...")

        # Use global VectorStoreManager instance to avoid creating new connection pools
        # This fixes the connection leak issue where each webhook created a new pool
        if _global_rag_pipeline and hasattr(_global_rag_pipeline, 'vector_store_manager'):
            vector_store_manager = _global_rag_pipeline.vector_store_manager
            logger.debug(f"🗑️ [Delete Task: {payload_id}] Using global VectorStoreManager instance")
        else:
            # Fallback: create new instance only if global not available
            vector_store_manager = VectorStoreManager()
            logger.warning(f"🗑️ [Delete Task: {payload_id}] Created new VectorStoreManager (global instance unavailable)")

        # Delete documents AND rebuild FAISS (since we're not adding new content)
        # For unpublish/delete, we need to rebuild to remove the deleted vectors
        deleted_count = vector_store_manager.delete_documents_by_metadata_field('payload_id', payload_id, rebuild_faiss=True)
        logger.info(f"🗑️ [Delete Task: {payload_id}] Deleted {deleted_count} document(s) and rebuilt FAISS index.")

        # Refresh the RAG pipeline to reload retrievers (this just reloads from disk now)
        try:
            if _global_rag_pipeline:
                _global_rag_pipeline.refresh_vector_store()
                logger.info(f"✅ [Delete Task: {payload_id}] RAG pipeline refreshed successfully")
            else:
                # Fallback: create new RAG pipeline instance
                rag_pipeline = RAGPipeline()
                rag_pipeline.refresh_vector_store()
                logger.info(f"✅ [Delete Task: {payload_id}] RAG pipeline refreshed successfully (new instance)")
        except Exception as refresh_error:
            logger.warning(f"⚠️ [Delete Task: {payload_id}] Failed to refresh RAG pipeline: {refresh_error}")

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"🎉 [Delete Task: {payload_id}] Deletion and refresh completed")
        
        if MONITORING_ENABLED:
            webhook_processing_duration_seconds.labels(
                source="payload_cms",
                operation=operation
            ).observe(duration)
            webhook_processing_total.labels(
                source="payload_cms",
                operation=operation,
                status="success"
            ).inc()

    except Exception as e:
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"💥 [Delete Task: {payload_id}] Deletion and refresh failed: {e}", exc_info=True)
        
        if MONITORING_ENABLED:
            webhook_processing_duration_seconds.labels(
                source="payload_cms",
                operation=operation
            ).observe(duration)
            webhook_processing_total.labels(
                source="payload_cms",
                operation=operation,
                status="error"
            ).inc()

def process_and_embed_document(payload_doc, operation="create"):
    """
    Background task to process and embed a single document from Payload.
    
    Supports FAQ indexing (Parent Document Pattern) when USE_FAQ_INDEXING=true.
    Synthetic questions are generated and indexed alongside the original chunks.
    
    CRUD Lifecycle: Synthetic questions inherit payload_id from parent chunk,
    so deletion by payload_id automatically removes both parent AND synthetic.
    
    Args:
        payload_doc: The Payload CMS document
        operation: The operation type ("create" or "update")
    """
    payload_id = payload_doc.id
    start_time = datetime.utcnow()

    try:
        logger.info(f"🚀 [Task ID: {payload_id}] Starting background processing for published document '{payload_doc.title}'")

        # Use global VectorStoreManager instance to avoid creating new connection pools
        # This fixes the connection leak issue where each webhook created a new pool
        logger.info(f"🔌 [Task ID: {payload_id}] Getting vector store connection...")
        if _global_rag_pipeline and hasattr(_global_rag_pipeline, 'vector_store_manager'):
            vector_store_manager = _global_rag_pipeline.vector_store_manager
            logger.debug(f"✅ [Task ID: {payload_id}] Using global VectorStoreManager instance (shared connection pool)")
        else:
            # Fallback: create new instance only if global not available
            vector_store_manager = VectorStoreManager()
            logger.warning(f"⚠️ [Task ID: {payload_id}] Created new VectorStoreManager (global instance unavailable)")
        logger.info(f"✅ [Task ID: {payload_id}] Vector store connected successfully")

        # 1. Delete existing documents for this payload_id to handle updates cleanly.
        # This removes BOTH original chunks AND synthetic questions (they share payload_id)
        logger.info(f"🗑️ [Task ID: {payload_id}] Deleting existing chunks from vector store...")
        deleted_count = vector_store_manager.delete_documents_by_metadata_field('payload_id', payload_id)
        logger.info(f"🗑️ [Task ID: {payload_id}] Deleted {deleted_count} existing chunk(s) (includes synthetic questions).")

        # 2. Process the new document into chunks with optional FAQ generation.
        # Check if FAQ indexing is enabled
        USE_FAQ_INDEXING = os.getenv("USE_FAQ_INDEXING", "true").lower() == "true"
        
        if USE_FAQ_INDEXING:
            logger.info(f"📝 [Task ID: {payload_id}] Processing document with FAQ generation (Parent Document Pattern)...")
            try:
                # Use asyncio.run to call the async FAQ processing function
                processed_chunks = asyncio.run(process_payload_documents_with_faq([payload_doc], generate_faq=True))
            except RuntimeError as e:
                # Handle case where event loop is already running (shouldn't happen in background task)
                if "already running" in str(e):
                    logger.warning(f"⚠️ [Task ID: {payload_id}] Event loop already running, falling back to sync processing")
                    processed_chunks = process_payload_documents([payload_doc])
                else:
                    raise
        else:
            logger.info(f"📝 [Task ID: {payload_id}] Processing document into hierarchical chunks (FAQ generation disabled)...")
            processed_chunks = process_payload_documents([payload_doc])

        if processed_chunks is None:
            logger.error(f"❌ [Task ID: {payload_id}] process_payload_documents returned None")
            return

        # Count synthetic questions vs original chunks
        synthetic_count = sum(1 for c in processed_chunks if c.metadata.get("is_synthetic", False))
        original_count = len(processed_chunks) - synthetic_count
        logger.info(f"📦 [Task ID: {payload_id}] Generated {original_count} chunks + {synthetic_count} synthetic questions")

        # 3. Add the new chunks to the vector store.
        if processed_chunks:
            logger.info(f"💾 [Task ID: {payload_id}] Adding {len(processed_chunks)} documents to the vector store...")
            vector_store_manager.add_documents(processed_chunks)
            logger.info(f"✅ [Task ID: {payload_id}] Successfully added {len(processed_chunks)} documents to the vector store.")
        else:
            logger.warning(f"⚠️ [Task ID: {payload_id}] No chunks were generated from the document.")

        # 4. Refresh the RAG pipeline to include the new documents
        logger.info(f"🔄 [Task ID: {payload_id}] Refreshing RAG pipeline with new documents...")
        try:
            if _global_rag_pipeline:
                _global_rag_pipeline.refresh_vector_store()
                logger.info(f"✅ [Task ID: {payload_id}] RAG pipeline refreshed successfully")
            else:
                # Fallback: create new RAG pipeline instance
                rag_pipeline = RAGPipeline()
                rag_pipeline.refresh_vector_store()
                logger.info(f"✅ [Task ID: {payload_id}] RAG pipeline refreshed successfully (new instance)")
        except Exception as refresh_error:
            logger.warning(f"⚠️ [Task ID: {payload_id}] Failed to refresh RAG pipeline: {refresh_error}")

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"🎉 [Task ID: {payload_id}] Background processing completed successfully in {duration:.2f} seconds")
        
        if MONITORING_ENABLED:
            webhook_processing_duration_seconds.labels(
                source="payload_cms",
                operation=operation
            ).observe(duration)
            webhook_processing_total.labels(
                source="payload_cms",
                operation=operation,
                status="success"
            ).inc()

    except Exception as e:
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"💥 [Task ID: {payload_id}] Background processing failed after {duration:.2f} seconds: {e}", exc_info=True)
        
        if MONITORING_ENABLED:
            webhook_processing_duration_seconds.labels(
                source="payload_cms",
                operation=operation
            ).observe(duration)
            webhook_processing_total.labels(
                source="payload_cms",
                operation=operation,
                status="error"
            ).inc()


@router.post("/payload")
async def receive_payload_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives a webhook from Payload CMS after a document is changed.
    Validates the payload and triggers a background task for processing if the document is published.
    
    Requires HMAC-SHA256 signature verification via X-Webhook-Signature header
    and timestamp validation via X-Webhook-Timestamp header.
    """
    try:
        # Read raw body for signature verification (can only be read once)
        body = await request.body()
        
        # Verify webhook signature and timestamp
        is_valid, error_message = await verify_webhook_request(request, body)
        if not is_valid:
            logger.warning(
                f"Webhook authentication failed: {error_message}. "
                f"IP: {request.client.host if request.client else 'unknown'}"
            )
            raise HTTPException(
                status_code=401,
                detail={"error": "Unauthorized", "message": "Invalid webhook signature or timestamp"}
            )
        
        # Log successful authentication
        logger.info(f"🔐 Webhook authentication successful - IP: {request.client.host if request.client else 'unknown'}")
        
        # Parse JSON payload after verification
        try:
            raw_payload = json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse webhook payload as JSON: {e}")
            raise HTTPException(status_code=400, detail={"error": "Invalid JSON payload"})
    except HTTPException:
        # Re-raise HTTP exceptions (they're already properly formatted)
        raise
    except Exception as e:
        # Catch any other exceptions to prevent connection reset
        logger.error(f"Unexpected error in webhook endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "An error occurred processing the webhook"}
        )
    
    logger.info(f"🔗 Received Payload webhook - Raw payload keys: {list(raw_payload.keys())}")

    try:
        # The webhook sends the 'doc' object directly, not the full PayloadWebhookPayload structure.
        # Extract the 'doc' and validate it against PayloadWebhookDoc.
        doc_data = raw_payload.get('doc', {})
        logger.info(f"📄 Document data keys: {list(doc_data.keys()) if isinstance(doc_data, dict) else 'Not a dict'}")

        # Normalize relationship fields to handle differences between create/update and delete hooks
        normalized_doc_data = normalize_relationship_fields(doc_data)
        logger.info(f"🔧 Normalized relationship fields for document processing")

        payload_doc = PayloadWebhookDoc(**normalized_doc_data)

        # Extract operation from payload, default to 'update'
        operation = raw_payload.get('operation', 'update')

        logger.info(f"📝 Processing doc ID '{payload_doc.id}' with status '{payload_doc.status}' and operation '{operation}'")
        logger.info(f"📖 Document title: '{payload_doc.title}'" if hasattr(payload_doc, 'title') and payload_doc.title else "📖 No title found")

        # Handle delete operations or non-published documents
        if operation == 'delete' or payload_doc.status != 'published':
            # Delete any existing chunks for this document and refresh RAG pipeline
            webhook_operation = 'delete' if operation == 'delete' else 'unpublish'
            from backend.jobs.enqueue import enqueue_delete
            try:
                await enqueue_delete(payload_doc.id, webhook_operation)
            except Exception as enqueue_error:
                logger.warning("ARQ enqueue failed, falling back to BackgroundTasks: %s", enqueue_error)
                background_tasks.add_task(delete_and_refresh_vector_store, payload_doc.id, webhook_operation)
            if operation == 'delete':
                msg = f"🗑️ DELETE operation: Document ID '{payload_doc.id}' deleted from CMS. Removing embeddings from FAISS and refreshing RAG pipeline."
                logger.info(msg)
            else:
                msg = f"🚫 Document ID '{payload_doc.id}' status changed to '{payload_doc.status}' (not published). Removing embeddings from FAISS and refreshing RAG pipeline."
                logger.info(msg)
            return {"status": "not_published_or_deleted", "message": msg, "document_id": payload_doc.id, "operation": operation}
        else:
            # Document is published and not deleted, process it
            # Run the processing in the background to avoid blocking the webhook response.
            webhook_operation = 'create' if operation == 'create' else 'update'
            from backend.jobs.enqueue import enqueue_ingest
            try:
                await enqueue_ingest(payload_doc.model_dump(mode="json"), webhook_operation)
            except Exception as enqueue_error:
                logger.warning("ARQ enqueue failed, falling back to BackgroundTasks: %s", enqueue_error)
                background_tasks.add_task(process_and_embed_document, payload_doc, webhook_operation)
            msg = f"✅ Processing triggered for published document ID: {payload_doc.id}"
            logger.info(msg)
            return {"status": "processing_triggered", "message": msg, "document_id": payload_doc.id}
    except ValidationError as e:
        logger.error(f"❌ Payload webhook validation error: {e.errors()}", exc_info=True)
        raise HTTPException(
            status_code=422,
            detail={"error": "Validation failed", "message": "Invalid webhook payload"}
        )
    except Exception as e:
        logger.error(f"💥 Unexpected error in Payload webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": "An error occurred processing the webhook"}
        )


@router.get("/health")
async def webhook_health_check():
    """
    Health check endpoint for webhook connectivity testing.
    """
    try:
        # Use global VectorStoreManager instance to avoid creating new connection pools
        if _global_rag_pipeline and hasattr(_global_rag_pipeline, 'vector_store_manager'):
            vector_store_manager = _global_rag_pipeline.vector_store_manager
        else:
            return {
                "status": "degraded",
                "error": "vector_store_manager not injected",
            }

        # Get total document count from MongoDB (documents have 'text' and 'metadata' fields)
        total_count = 0
        payload_count = 0

        if vector_store_manager.mongodb_available:
            total_count = vector_store_manager.collection.count_documents({})
            # Count documents that have payload_id in metadata (Payload CMS sourced)
            payload_count = vector_store_manager.collection.count_documents({
                "metadata.payload_id": {"$exists": True}
            })

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "vector_store": "connected",
                "mongodb": "available" if vector_store_manager.mongodb_available else "unavailable"
            },
            "document_counts": {
                "total": total_count,
                "from_payload_cms": payload_count
            },
            "message": "Webhook service is operational"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Webhook service has issues"
        }


@router.post("/test-webhook")
async def test_webhook_endpoint(request: Request):
    """
    Test endpoint to simulate webhook payload for debugging.
    
    In production, this endpoint is disabled or requires authentication.
    """
    # Check if we're in production
    node_env = os.getenv("NODE_ENV", "").lower()
    is_production = node_env == "production"
    
    if is_production:
        logger.warning(
            f"Test webhook endpoint accessed in production. "
            f"IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "Not found"}
        )
    
    # In development, require webhook authentication if WEBHOOK_SECRET is set
    body = await request.body()
    payload = None
    
    # If WEBHOOK_SECRET is configured, require authentication
    if os.getenv("WEBHOOK_SECRET"):
        is_valid, error_message = await verify_webhook_request(request, body)
        if not is_valid:
            logger.warning(f"Test webhook authentication failed: {error_message}")
            raise HTTPException(
                status_code=401,
                detail={"error": "Unauthorized", "message": "Invalid webhook signature or timestamp"}
            )
    
    # Parse JSON payload
    try:
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Failed to parse test webhook payload as JSON: {e}")
        raise HTTPException(status_code=400, detail={"error": "Invalid JSON payload"})
    
    try:
        logger.info(f"🧪 Test webhook received: {payload}")

        # Validate the payload structure
        doc_data = payload.get('doc', {})
        if not doc_data:
            return {"status": "error", "message": "Missing 'doc' field in payload"}

        # Normalize relationship fields to handle test payloads that might have object formats
        normalized_doc_data = normalize_relationship_fields(doc_data)

        # Try to validate against our model
        payload_doc = PayloadWebhookDoc(**normalized_doc_data)

        return {
            "status": "success",
            "message": f"Test webhook processed successfully for document '{payload_doc.title}' (ID: {payload_doc.id})",
            "document_id": payload_doc.id,
            "document_status": payload_doc.status
        }
    except ValidationError as e:
        logger.error(f"Test webhook validation error: {e.errors()}")
        return {"status": "validation_error", "errors": e.errors()}
    except Exception as e:
        logger.error(f"Test webhook error: {e}")
        return {"status": "error", "message": str(e)}
