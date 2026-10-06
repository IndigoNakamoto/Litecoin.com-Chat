"""ARQ task functions. Worker executes these; the API only enqueues."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_script(relpath: str, extra_args: List[str] | None = None) -> None:
    cmd = [sys.executable, str(PROJECT_ROOT / relpath), *(extra_args or [])]
    logger.info("Running %s", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))


class IngestProducedNoChunks(RuntimeError):
    """A published article finished ingest with zero chunks in the vector store."""


def _stored_chunk_count(payload_id: str) -> Optional[int]:
    """Chunks in `litecoin_docs` for this article, or None when it cannot be checked."""
    try:
        from backend.api.v1.sync import payload as sync_payload

        pipeline = getattr(sync_payload, "_global_rag_pipeline", None)
        manager = getattr(pipeline, "vector_store_manager", None)
        if manager is None:
            from backend.data_ingestion.vector_store_manager import VectorStoreManager

            manager = VectorStoreManager()
        count = getattr(manager, "count_documents_by_metadata_field", None)
        return count("payload_id", payload_id) if callable(count) else None
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not verify chunk count for payload_id=%s: %s", payload_id, e)
        return None


async def ingest_payload_document(ctx: Dict[str, Any], doc_dict: Dict[str, Any], operation: str) -> Dict[str, Any]:
    """Chunk + embed one CMS article.

    `process_and_embed_document` logs and swallows its own errors (it predates the
    worker), so the ARQ job used to report success even when nothing was stored —
    three Litecoin Dev Kit READMEs landed with no chunks during the 2026-10-05 bulk
    publish. We now count what actually reached `litecoin_docs` and raise when a
    published article produced nothing, so ARQ retries and the Jobs page shows it.
    """
    from backend.api.v1.sync.payload import process_and_embed_document
    from backend.data_models import PayloadWebhookDoc

    doc = PayloadWebhookDoc(**doc_dict)
    await asyncio.to_thread(process_and_embed_document, doc, operation)

    chunks = await asyncio.to_thread(_stored_chunk_count, doc.id) if doc.status == "published" else None
    if doc.status == "published" and chunks == 0:
        raise IngestProducedNoChunks(
            f"payload_id={doc.id} ({doc.title!r}) is published but has 0 chunks after ingest"
        )
    return {"payload_id": doc.id, "status": doc.status, "chunks": chunks}


async def delete_payload_document(ctx: Dict[str, Any], payload_id: str, operation: str) -> None:
    from backend.api.v1.sync.payload import delete_and_refresh_vector_store

    await asyncio.to_thread(delete_and_refresh_vector_store, payload_id, operation)


async def reindex_vectors(ctx: Dict[str, Any]) -> None:
    await asyncio.to_thread(_run_script, "scripts/reindex_vectors.py")


async def reindex_with_faq(ctx: Dict[str, Any]) -> None:
    await asyncio.to_thread(_run_script, "scripts/reindex_with_faq.py")


async def refresh_suggested_questions(ctx: Dict[str, Any]) -> None:
    from backend.main import refresh_suggested_question_cache

    await refresh_suggested_question_cache()


async def cleanup_orphans(ctx: Dict[str, Any]) -> None:
    await asyncio.to_thread(_run_script, "backend/utils/cleanup_orphaned_embeddings.py", ["--force"])
