from __future__ import annotations

import logging
from typing import Any, Dict

from ..state import RAGState

logger = logging.getLogger(__name__)


def make_prechecks_node(pipeline: Any):
    async def prechecks(state: RAGState) -> RAGState:
        """
        Prechecks: intent (optional) and exact cache check.

        We keep this conservative: if integrations aren't configured on the pipeline yet,
        this node becomes a no-op.
        """
        query_text = state.get("sanitized_query") or state.get("raw_query") or ""
        effective_history = state.get("effective_history_pairs") or []
        is_dependent = bool(state.get("is_dependent", False))

        metadata: Dict[str, Any] = state.get("metadata") or {}

        # 1) Intent/static responses (optional)
        if getattr(pipeline, "use_intent_classification", False):
            intent_classifier = pipeline.get_intent_classifier() if hasattr(pipeline, "get_intent_classifier") else None
            if intent_classifier:
                try:
                    from backend.services.intent_classifier import Intent

                    intent, matched_faq, static_response = intent_classifier.classify(query_text)
                    state["intent"] = getattr(intent, "value", str(intent))
                    state["matched_faq"] = matched_faq

                    # Blockchain lookups always proceed (live data, independent of history)
                    if intent == Intent.BLOCKCHAIN_LOOKUP:
                        logger.info(f"Blockchain lookup detected (is_dependent={is_dependent}): {matched_faq}")
                        state["metadata"] = metadata
                        return state

                    # Greeting/thanks/FAQ short-circuits only for independent queries
                    if not is_dependent:
                        if intent in (Intent.GREETING, Intent.THANKS) and static_response:
                            state.update(
                                {
                                    "early_answer": static_response,
                                    "early_sources": [],
                                    "early_cache_type": f"intent_{intent.value}",
                                }
                            )
                            metadata.update(
                                {
                                    "input_tokens": 0,
                                    "output_tokens": 0,
                                    "cost_usd": 0.0,
                                    "cache_hit": True,
                                    "cache_type": state["early_cache_type"],
                                    "intent": intent.value,
                                }
                            )
                            state["metadata"] = metadata
                            return state

                        # FAQ match: try suggested question cache (if available)
                        if intent == Intent.FAQ_MATCH and matched_faq:
                            suggested_cache = (
                                pipeline.get_suggested_question_cache()
                                if hasattr(pipeline, "get_suggested_question_cache")
                                else None
                            )
                            if suggested_cache and hasattr(suggested_cache, "get"):
                                cached = await suggested_cache.get(matched_faq)
                                if cached:
                                    answer, sources = cached
                                    # Skip entries that only contain the generic error message
                                    if answer and answer.strip() != getattr(pipeline, "generic_user_error_message", ""):
                                        state.update(
                                            {
                                                "early_answer": answer,
                                                "early_sources": sources,
                                                "early_cache_type": "intent_faq_match",
                                            }
                                        )
                                        metadata.update(
                                            {
                                                "input_tokens": 0,
                                                "output_tokens": 0,
                                                "cost_usd": 0.0,
                                                "cache_hit": True,
                                                "cache_type": "intent_faq_match",
                                                "intent": "faq_match",
                                                "matched_faq": matched_faq,
                                            }
                                        )
                                        state["metadata"] = metadata
                                        return state
                except Exception:
                    # Best-effort only; fall through to normal flow.
                    pass

        # 2) Exact cache check (optional)
        query_cache = getattr(pipeline, "query_cache", None)
        if query_cache and hasattr(query_cache, "get"):
            try:
                cached = query_cache.get(query_text, effective_history)
                if cached:
                    answer, sources = cached
                    state.update(
                        {
                            "early_answer": answer,
                            "early_sources": sources,
                            "early_cache_type": "exact",
                        }
                    )
                    metadata.update(
                        {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cost_usd": 0.0,
                            "cache_hit": True,
                            "cache_type": "exact",
                        }
                    )
                    state["metadata"] = metadata
                    return state
            except Exception:
                pass

        # 3) Set rewritten query defaults for downstream nodes
        effective_query = state.get("effective_query") or query_text
        expanded_query = effective_query

        from backend.utils.litecoin_vocabulary import expand_ltc_entities, normalize_ltc_keywords

        def _vocab_expand(text: str) -> str:
            try:
                return expand_ltc_entities(normalize_ltc_keywords(text or "")).strip()
            except Exception:
                return (text or "").strip()

        vocab_expanded = _vocab_expand(effective_query)
        vocab_changed = vocab_expanded.lower() != (effective_query or "").strip().lower()

        # 3a) Short-query expansion: vocab first. LLM only if vocab did not change the query
        # (not a string-length check — normalize can canonicalize without growing).
        if (
            getattr(pipeline, "use_short_query_expansion", False)
            and not is_dependent
            and effective_query
        ):
            try:
                import re
                from collections import OrderedDict
                from langchain_core.messages import HumanMessage, SystemMessage

                tokens = re.findall(r"[a-z0-9']+", effective_query.lower())
                short_threshold = int(getattr(pipeline, "short_query_word_threshold", 3) or 3)

                if 0 < len(tokens) <= short_threshold:
                    logger.info("Short query detected (≤%s tokens): %r", short_threshold, effective_query)
                    if vocab_changed:
                        expanded_query = vocab_expanded
                        metadata.update(
                            {
                                "short_query_expanded": True,
                                "short_query_original": effective_query,
                                "short_query_expanded_query": expanded_query,
                                "short_query_expand_source": "vocab",
                            }
                        )
                        logger.info(
                            "Short query expanded via vocab (no LLM): %r -> %r",
                            effective_query,
                            expanded_query,
                        )
                    elif getattr(pipeline, "llm", None) is not None:
                        cache_key = effective_query.strip().lower()
                        cache_max = int(getattr(pipeline, "short_query_expansion_cache_max", 512) or 512)
                        max_words = int(getattr(pipeline, "short_query_expansion_max_words", 12) or 12)

                        if getattr(pipeline, "short_query_expansion_cache", None) is None:
                            pipeline.short_query_expansion_cache = OrderedDict()  # type: ignore[attr-defined]
                        cache = pipeline.short_query_expansion_cache  # type: ignore[attr-defined]

                        if isinstance(cache, OrderedDict) and cache_key in cache:
                            expanded_query = cache[cache_key]
                            cache.move_to_end(cache_key)
                            logger.info(
                                "Short query expansion (cache hit): %r -> %r",
                                effective_query,
                                expanded_query,
                            )
                        else:
                            llm = pipeline.llm
                            sys = (
                                "You expand very short user queries for retrieval in a Litecoin knowledge base.\n"
                                "Return ONLY the expanded query text (no quotes, no markdown). "
                                "Keep it concise and specific to Litecoin."
                            )
                            human = (
                                f"Short query: {effective_query}\n\n"
                                "Expand it into a concise standalone question (5–12 words). "
                                "If the query is an acronym or term (e.g., MWEB, LitVM, halving), expand it."
                            )
                            logger.info("Expanding short query via LLM: %r", effective_query)
                            result = await llm.ainvoke(
                                [SystemMessage(content=sys), HumanMessage(content=human)]
                            )
                            candidate = getattr(result, "content", None) or str(result)
                            candidate = candidate.strip().strip('"').strip("'")
                            candidate = re.sub(r"\s+", " ", candidate).strip()
                            if candidate:
                                words = candidate.split()
                                if len(words) > max_words:
                                    candidate = " ".join(words[:max_words]).strip()
                                if candidate and candidate.lower() != effective_query.strip().lower():
                                    expanded_query = candidate
                                    if isinstance(cache, OrderedDict):
                                        cache[cache_key] = expanded_query
                                        cache.move_to_end(cache_key)
                                        while len(cache) > cache_max:
                                            cache.popitem(last=False)
                                    metadata.update(
                                        {
                                            "short_query_expanded": True,
                                            "short_query_original": effective_query,
                                            "short_query_expanded_query": expanded_query,
                                            "short_query_expand_source": "llm",
                                        }
                                    )
                                    logger.info(
                                        "Short query expanded via LLM: %r -> %r",
                                        effective_query,
                                        expanded_query,
                                    )
            except Exception as e:
                logger.warning("Short query expansion failed: %s", e, exc_info=True)

        rewritten_expanded = _vocab_expand(expanded_query)
        state["rewritten_query"] = rewritten_expanded
        state["rewritten_query_for_cache"] = rewritten_expanded
        state["retrieval_query"] = rewritten_expanded
        state["metadata"] = metadata
        return state

    return prechecks


