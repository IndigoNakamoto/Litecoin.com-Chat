from __future__ import annotations

from typing import Any, Dict, List

from fastapi import HTTPException

from langchain_core.messages import BaseMessage

from ..state import RAGState


def make_spend_limit_node(pipeline: Any):
    async def spend_limit(state: RAGState) -> RAGState:
        """
        Pre-flight spend limit check.

        Mirrors the current `aquery`/`astream_query` pre-flight check: estimate max cost
        from prompt+history+context, then reject with HTTP 429 if limit exceeded.
        """
        metadata: Dict[str, Any] = state.get("metadata") or {}

        if state.get("early_answer") is not None or state.get("error_message") is not None:
            state["metadata"] = metadata
            return state

        if not getattr(pipeline, "monitoring_enabled", False):
            state["metadata"] = metadata
            return state

        query_text = state.get("sanitized_query") or state.get("raw_query") or ""
        context_docs = state.get("context_docs") or []
        chat_history: List[BaseMessage] = state.get("converted_history_messages") or []

        # If we don't have context, there's nothing to estimate; allow.
        if not context_docs:
            state["metadata"] = metadata
            return state

        try:
            # Rebuild prompt text for estimation (include chat history)
            context_text = "\n\n".join(d.page_content for d in context_docs)
            prompt_text = pipeline._build_prompt_text_with_history(query_text, context_text, chat_history)  # type: ignore[attr-defined]
            input_tokens_est, _ = pipeline._estimate_token_usage(prompt_text, "")  # type: ignore[attr-defined]
            max_output_tokens = 4096
            estimated_cost = pipeline.estimate_gemini_cost(input_tokens_est, max_output_tokens, pipeline.model_name)

            allowed, error_msg, _ = await pipeline.check_spend_limit(estimated_cost, pipeline.model_name)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "spend_limit_exceeded",
                        "message": "We've reached our daily usage limit. Please try again later.",
                        "type": "daily" if "daily" in str(error_msg).lower() else "hourly",
                    },
                )
        except HTTPException:
            raise
        except Exception:
            # Graceful degradation: do not block requests on spend-limit check failures.
            pass

        state["metadata"] = metadata
        return state

    return spend_limit


