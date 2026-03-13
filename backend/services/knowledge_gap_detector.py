"""
Knowledge Gap Detector

Detects when search grounding was used to fill KB gaps, deduplicates
against existing candidates, and queues new candidates for admin review.

Part of the Knowledge Gap Flywheel: user questions that expose missing
KB content are captured so admins can publish them as Payload CMS articles,
permanently closing the gap.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from backend.dependencies import get_knowledge_candidates_collection
from backend.data_models import KnowledgeCandidate

logger = logging.getLogger(__name__)

DEDUP_SIMILARITY_THRESHOLD = 0.90
PROVENANCE_MARKER = "Based on public sources:"

try:
    from backend.monitoring.metrics import (
        knowledge_candidates_total,
        knowledge_candidates_deduped_total,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = np.dot(va, vb)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def _extract_grounding_sources(grounding_metadata: Optional[Dict]) -> List[Dict[str, Any]]:
    """Extract web source URLs/titles from Gemini grounding metadata."""
    if not grounding_metadata:
        return []

    sources: List[Dict[str, Any]] = []
    chunks = grounding_metadata.get("grounding_chunks") or []
    for chunk in chunks:
        web = chunk.get("web") if isinstance(chunk, dict) else None
        if web:
            sources.append({
                "url": web.get("uri", ""),
                "title": web.get("title", ""),
            })
    return sources


def _detect_topic_cluster(question: str) -> Optional[str]:
    """Fast heuristic topic detection using canonical Litecoin terms."""
    q = question.lower()
    topic_patterns = {
        "mweb": r"\bmweb\b|mimblewimble|extension block|privacy",
        "litvm": r"\blitvm\b|litecoin virtual machine|smart contract|zk.?rollup",
        "mining": r"\bmin(?:ing|er|e)\b|hashrate|scrypt|proof of work|asic",
        "halving": r"\bhalv(?:ing|ening)\b|block reward|supply|emission",
        "lightning": r"\blightning\b|payment channel|layer.?2",
        "transactions": r"\btransaction|block.?time|fee|mempool|utxo",
        "history": r"\bhistory|created|founded|origin|charlie lee|creator",
        "wallets": r"\bwallet|address|seed|private key|public key",
    }
    for topic, pattern in topic_patterns.items():
        if re.search(pattern, q):
            return topic
    return None


def _determine_gap_trigger(
    grounding_metadata: Optional[Dict],
    published_sources_count: int,
    answer_text: str,
    grounded_profile: bool = False,
) -> Optional[str]:
    """
    Determine which gap signal triggered candidacy.
    Returns the trigger name or None if no gap detected.
    """
    if grounding_metadata and grounding_metadata.get("grounding_chunks"):
        return "grounding"
    if grounded_profile:
        return "grounded_chain"
    if published_sources_count == 0:
        return "no_kb_sources"
    if PROVENANCE_MARKER in answer_text:
        return "provenance_marker"
    return None


async def detect_and_queue_knowledge_gap(
    request_id: str,
    user_question: str,
    generated_answer: str,
    published_sources_count: int,
    retriever_k: int,
    grounding_metadata: Optional[Dict],
    embedding_model: Any,
    kb_sources: Optional[List[Dict[str, Any]]] = None,
    grounded_profile: bool = False,
) -> Optional[str]:
    """
    Detect a knowledge gap and queue a candidate for admin review.

    Returns the candidate ID if a new candidate was created, or None if
    the gap was deduplicated or no gap was detected.
    """
    trigger = _determine_gap_trigger(grounding_metadata, published_sources_count, generated_answer, grounded_profile)
    if trigger is None:
        return None

    logger.info(
        "Knowledge gap detected: trigger=%s, question='%s', sources=%d/%d",
        trigger, user_question[:80], published_sources_count, retriever_k,
    )

    try:
        collection = await get_knowledge_candidates_collection()
    except Exception as e:
        logger.error("Failed to access knowledge_candidates collection: %s", e)
        return None

    # Embed the question for dedup
    question_embedding: Optional[List[float]] = None
    try:
        if hasattr(embedding_model, "embed_query"):
            question_embedding = embedding_model.embed_query(user_question)
    except Exception as e:
        logger.warning("Failed to embed candidate question for dedup: %s", e)

    # Dedup: check existing pending/approved candidates
    if question_embedding:
        try:
            existing_cursor = collection.find(
                {"status": {"$in": ["pending", "approved"]}, "question_embedding": {"$exists": True}},
                {"question_embedding": 1, "question_frequency": 1, "similar_candidate_ids": 1},
            ).limit(500)

            async for existing in existing_cursor:
                existing_emb = existing.get("question_embedding")
                if not existing_emb or len(existing_emb) != len(question_embedding):
                    continue

                sim = _cosine_similarity(question_embedding, existing_emb)
                if sim >= DEDUP_SIMILARITY_THRESHOLD:
                    existing_id = str(existing["_id"])
                    await collection.update_one(
                        {"_id": existing["_id"]},
                        {
                            "$inc": {"question_frequency": 1},
                            "$addToSet": {"similar_candidate_ids": request_id},
                        },
                    )
                    logger.info(
                        "Deduped knowledge candidate: existing=%s, sim=%.3f, freq=%d",
                        existing_id, sim, existing.get("question_frequency", 1) + 1,
                    )
                    if METRICS_AVAILABLE:
                        knowledge_candidates_deduped_total.inc()
                    return None
        except Exception as e:
            logger.warning("Dedup check failed, proceeding with insert: %s", e)

    # Build candidate
    kb_coverage = min(published_sources_count / max(retriever_k, 1), 1.0)
    grounding_sources = _extract_grounding_sources(grounding_metadata)
    topic = _detect_topic_cluster(user_question)

    candidate = KnowledgeCandidate(
        user_question=user_question,
        request_id=request_id,
        generated_answer=generated_answer,
        grounding_sources=grounding_sources,
        kb_sources_used=kb_sources or [],
        kb_coverage_score=kb_coverage,
        topic_cluster=topic,
        question_embedding=question_embedding,
    )

    try:
        result = await collection.insert_one(candidate.model_dump(exclude={"id"}))
        candidate_id = str(result.inserted_id)
        logger.info(
            "Knowledge candidate created: id=%s, topic=%s, coverage=%.2f, trigger=%s",
            candidate_id, topic, kb_coverage, trigger,
        )
        if METRICS_AVAILABLE:
            knowledge_candidates_total.labels(trigger=trigger).inc()
        return candidate_id
    except Exception as e:
        logger.error("Failed to insert knowledge candidate: %s", e, exc_info=True)
        return None
