"""ARQ task functions. Worker executes these; the API only enqueues."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_script(relpath: str, extra_args: List[str] | None = None) -> None:
    cmd = [sys.executable, str(PROJECT_ROOT / relpath), *(extra_args or [])]
    logger.info("Running %s", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))


async def ingest_payload_document(ctx: Dict[str, Any], doc_dict: Dict[str, Any], operation: str) -> None:
    from backend.api.v1.sync.payload import process_and_embed_document
    from backend.data_models import PayloadWebhookDoc

    doc = PayloadWebhookDoc(**doc_dict)
    await asyncio.to_thread(process_and_embed_document, doc, operation)


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
