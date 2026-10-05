"""
Stage markers for the streaming UI.

`RAGPipeline._run_graph_with_stages` observes LangGraph node completions and
yields ("stage", name) before ("state", final_state):
  - prechecks routes to the live-data node   -> "checking_live_data"
  - semantic_cache misses (retrieval next)   -> "searching"
Cache hits / early answers emit no stage. The "writing" marker is emitted by
`astream_query` right before generation (covered in test_astream_query).
"""
from typing import Any, Dict

import pytest

from backend.rag_graph.graph import build_rag_graph
from backend.rag_pipeline import RAGPipeline


def _passthrough(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def _nodes(**overrides):
    names = [
        "sanitize_normalize", "safety_gate", "route", "prechecks", "semantic_cache",
        "decompose", "retrieve", "resolve_parents", "spend_limit", "generate", "blockchain_lookup",
    ]
    nodes = {n: _passthrough for n in names}
    nodes.update(overrides)
    return nodes


def _pipeline_with_graph(graph):
    p = object.__new__(RAGPipeline)
    p._get_rag_graph = lambda: graph
    return p


async def _collect(pipeline):
    stages, state = [], None
    async for kind, payload in pipeline._run_graph_with_stages({"raw_query": "q", "chat_history_pairs": [], "metadata": {}}):
        if kind == "stage":
            stages.append(payload)
        else:
            state = payload
    return stages, state


@pytest.mark.asyncio
async def test_cache_miss_emits_searching_stage():
    def retrieve(state):
        state["published_sources"] = ["doc"]
        return state

    graph = build_rag_graph(_nodes(retrieve=retrieve))
    stages, state = await _collect(_pipeline_with_graph(graph))
    assert stages == ["searching"]
    assert state["published_sources"] == ["doc"]


@pytest.mark.asyncio
async def test_blockchain_route_emits_checking_live_data_stage():
    def prechecks(state):
        state["intent"] = "blockchain_lookup"
        return state

    def blockchain_lookup(state):
        state["early_answer"] = "live"
        return state

    graph = build_rag_graph(_nodes(prechecks=prechecks, blockchain_lookup=blockchain_lookup))
    stages, state = await _collect(_pipeline_with_graph(graph))
    assert stages == ["checking_live_data"]
    assert state["early_answer"] == "live"


@pytest.mark.asyncio
async def test_semantic_cache_hit_emits_no_stage():
    def semantic_cache(state):
        state["early_answer"] = "cached"
        return state

    graph = build_rag_graph(_nodes(semantic_cache=semantic_cache))
    stages, state = await _collect(_pipeline_with_graph(graph))
    assert stages == []
    assert state["early_answer"] == "cached"


@pytest.mark.asyncio
async def test_graph_double_without_astream_falls_back_to_ainvoke():
    class _Graph:
        async def ainvoke(self, _):
            return {"early_answer": "x"}

    stages, state = await _collect(_pipeline_with_graph(_Graph()))
    assert stages == []
    assert state == {"early_answer": "x"}
