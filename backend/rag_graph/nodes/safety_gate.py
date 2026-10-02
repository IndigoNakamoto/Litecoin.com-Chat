"""
Safety gate node: incident pin, refuse/escalate, audience label.

Runs right after `sanitize_normalize`, *before* routing, caching, and retrieval:

1. Incident pin (Redis `admin:incident_pin`): when set and matching, the pinned
   answer is served and nothing else runs. Never cached.
2. Refuse / Escalate: regex-first classifier (see `services/safety_router.py`).
   Prompt-injection hits from the sanitizer are treated as REFUSE here instead
   of being silently discarded.
3. Audience: a label (newcomer | holder | merchant | developer | journalist) that
   later picks the response-length profile. Scope never changes with audience.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend.utils.input_sanitizer import detect_prompt_injection

from ..state import RAGState

logger = logging.getLogger(__name__)


def _inc(counter_name: str, **labels: str) -> None:
    try:
        from backend.monitoring import metrics as m

        counter = getattr(m, counter_name)
        (counter.labels(**labels) if labels else counter).inc()
    except Exception:
        pass


def make_safety_gate_node(pipeline: Any):
    async def safety_gate(state: RAGState) -> RAGState:
        metadata: Dict[str, Any] = state.get("metadata") or {}
        raw_query = state.get("raw_query") or ""
        query = state.get("sanitized_query") or raw_query
        history = state.get("truncated_history_pairs") or state.get("chat_history_pairs") or []

        # --- 1) Incident pin --------------------------------------------------
        redis_client = None
        if hasattr(pipeline, "get_redis_client"):
            try:
                redis_client = await pipeline.get_redis_client()
            except Exception as e:  # noqa: BLE001
                logger.debug("safety_gate: redis unavailable (%s); skipping incident pin", e)
        if redis_client is not None:
            try:
                from backend.services.incident_pin import get_pin

                pin = await get_pin(redis_client)
                if pin is not None and pin.matches(query):
                    from langchain_core.documents import Document

                    sources = [
                        Document(
                            page_content="",
                            metadata={
                                "status": "published",
                                "doc_title": s.get("title") or pin.title,
                                "slug": None,
                                "payload_id": None,
                                "source_tier": "pinned",
                                "pinned_url": s.get("url"),
                            },
                        )
                        for s in (pin.sources or [])
                        if isinstance(s, dict)
                    ]
                    state.update(
                        {
                            "early_answer": pin.answer,
                            "early_sources": sources,
                            "early_cache_type": "incident_pin",
                            "incident_pin_id": pin.id,
                            "intent": "incident_pin",
                        }
                    )
                    metadata.update(
                        {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cost_usd": 0.0,
                            "cache_hit": False,
                            "cache_type": "incident_pin",
                            "intent": "incident_pin",
                            "incident_pin_id": pin.id,
                            "incident_pin_title": pin.title,
                        }
                    )
                    _inc("incident_pin_served_total")
                    logger.warning("Serving incident pin %s for query=%r", pin.id, query[:80])
                    state["metadata"] = metadata
                    return state
            except Exception as e:  # noqa: BLE001
                logger.warning("safety_gate: incident pin check failed: %s", e)

        # --- 2) Refuse / Escalate --------------------------------------------
        injection, pattern = detect_prompt_injection(raw_query)
        from backend.services.safety_router import classify_safety, decide

        # The sanitizer may have rewritten the text; classify the raw query too so a
        # neutralised injection attempt is still refused rather than answered.
        if not injection and classify_safety(raw_query) == ("refuse", "prompt_injection"):
            injection, pattern = True, "safety_router"
        if injection:
            metadata["prompt_injection_pattern"] = pattern

        decision = await decide(
            query,
            history_pairs=history,
            llm=getattr(pipeline, "llm", None),
            injection_detected=bool(injection),
        )

        if decision.audience:
            state["audience"] = decision.audience
            metadata["audience"] = decision.audience

        if decision.intent in ("refuse", "escalate") and decision.answer:
            state.update(
                {
                    "early_answer": decision.answer,
                    "early_sources": [],
                    "early_cache_type": f"intent_{decision.intent}",
                    "intent": decision.intent,
                }
            )
            metadata.update(
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "cache_hit": False,
                    "cache_type": f"intent_{decision.intent}",
                    "intent": decision.intent,
                    "safety_category": decision.category,
                }
            )
            _inc("rag_refuse_total", category=decision.category or decision.intent)
            logger.info("safety_gate: %s (%s) for query=%r", decision.intent, decision.category, query[:80])

        state["metadata"] = metadata
        return state

    return safety_gate
