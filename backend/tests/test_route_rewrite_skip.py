"""Rewrite skip: is_dependent === frozen tokens/prefixes. No Gemini just-in-case."""

import pytest

from backend.rag.history_dependency import STRONG_AMBIGUOUS_TOKENS, STRONG_PREFIXES, is_obviously_dependent
from backend.rag_graph.nodes.route import make_route_node


CHARLIE_HISTORY = [("Who is charlie?", "Charlie Lee created Litecoin.")]


class _RewritePipeline:
    def __init__(self):
        self.strong_ambiguous_tokens = STRONG_AMBIGUOUS_TOKENS
        self.strong_prefixes = STRONG_PREFIXES
        self.rewrite_calls = 0

    async def _semantic_history_check(self, query_text, chat_history):
        self.rewrite_calls += 1
        return f"REWRITTEN:{query_text}", True


def _base_state(query: str, history=None):
    return {
        "raw_query": query,
        "sanitized_query": query,
        "normalized_query": query,
        "truncated_history_pairs": history or [],
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_standalone_followup_skips_rewrite_and_drops_history():
    pipeline = _RewritePipeline()
    node = make_route_node(pipeline)
    state = await node(_base_state("What is the purpose of the foundation?", CHARLIE_HISTORY))

    assert pipeline.rewrite_calls == 0
    assert state["is_dependent"] is False
    assert state["effective_history_pairs"] == []
    assert state["converted_history_messages"] == []
    assert state["metadata"].get("history_rewrite_skipped") is True
    assert "foundation" in (state.get("effective_query") or "").lower()


@pytest.mark.asyncio
async def test_obvious_pronoun_still_calls_rewrite():
    pipeline = _RewritePipeline()
    node = make_route_node(pipeline)

    for query in ("what about it?", "who is he?"):
        pipeline.rewrite_calls = 0
        state = await node(_base_state(query, CHARLIE_HISTORY))
        assert is_obviously_dependent(query)
        assert pipeline.rewrite_calls == 1
        assert state["is_dependent"] is True
        assert state["effective_history_pairs"] == CHARLIE_HISTORY
        assert state["metadata"].get("history_rewrite_skipped") is not True


@pytest.mark.asyncio
async def test_entity_only_foundation_skips_rewrite():
    pipeline = _RewritePipeline()
    node = make_route_node(pipeline)
    state = await node(_base_state("foundation?", CHARLIE_HISTORY))

    assert pipeline.rewrite_calls == 0
    assert state["is_dependent"] is False
    assert "foundation" in (state.get("effective_query") or "").lower()
    # Vocab expand on the rewrite-skip path
    assert "litecoin" in (state.get("effective_query") or "").lower() or "lf" in (
        state.get("effective_query") or ""
    ).lower()


@pytest.mark.asyncio
async def test_false_independence_the_second_one_is_accepted_degraded():
    """Documented miss: 'the second one' looks standalone and is not in the frozen lists."""
    assert not is_obviously_dependent("the second one")
    pipeline = _RewritePipeline()
    node = make_route_node(pipeline)
    state = await node(_base_state("the second one", CHARLIE_HISTORY))

    assert pipeline.rewrite_calls == 0
    assert state["is_dependent"] is False
    assert state["effective_history_pairs"] == []
    assert state["metadata"].get("history_rewrite_skipped") is True


def test_frozen_lists_are_the_shared_source():
    assert "it" in STRONG_AMBIGUOUS_TOKENS
    assert "he" in STRONG_AMBIGUOUS_TOKENS
    assert any(p.startswith("what about") for p in STRONG_PREFIXES)
    assert is_obviously_dependent("and the fees?")
    assert not is_obviously_dependent("same for MWEB?")
