from __future__ import annotations

import logging
from typing import Any, Dict

from ..state import RAGState

logger = logging.getLogger(__name__)


def make_generate_node(pipeline: Any):
    async def generate(state: RAGState) -> RAGState:
        """Thin graph node: non-stream generation via `backend.rag.generate`.

        Streaming callers set `skip_generation` so `astream_query` still owns the chain.
        Early exits and empty published sources leave `generated_answer` unset.
        """
        metadata: Dict[str, Any] = state.get("metadata") or {}

        if state.get("skip_generation"):
            state["metadata"] = metadata
            return state
        if state.get("early_answer") is not None or state.get("error_message") is not None:
            state["metadata"] = metadata
            return state
        if not state.get("published_sources"):
            state["metadata"] = metadata
            return state

        try:
            from backend.rag.generate import generate_answer

            return await generate_answer(pipeline, state)
        except Exception as e:
            logger.warning("Generate node failed; pipeline may fall back: %s", e, exc_info=True)
            state["metadata"] = metadata
            return state

    return generate
