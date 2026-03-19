from __future__ import annotations

from typing import Any, Callable, Dict

from langgraph.graph import END, StateGraph

from .state import RAGState


def build_rag_graph(nodes: Dict[str, Callable[..., Any]]):
    """
    Build and compile a LangGraph graph for the RAG pipeline.

    `nodes` is an injected mapping so we can unit-test the graph wiring and
    also avoid circular imports between pipeline and graph.
    """
    graph = StateGraph(RAGState)

    # Core nodes (names are part of our internal contract)
    graph.add_node("sanitize_normalize", nodes["sanitize_normalize"])
    graph.add_node("route", nodes["route"])
    graph.add_node("prechecks", nodes["prechecks"])  # intent + exact cache + embedding kickoff
    graph.add_node("semantic_cache", nodes["semantic_cache"])
    graph.add_node("decompose", nodes["decompose"])
    graph.add_node("retrieve", nodes["retrieve"])
    graph.add_node("resolve_parents", nodes["resolve_parents"])
    graph.add_node("spend_limit", nodes["spend_limit"])
    graph.add_node("blockchain_lookup", nodes["blockchain_lookup"])

    graph.set_entry_point("sanitize_normalize")
    graph.add_edge("sanitize_normalize", "route")
    graph.add_edge("route", "prechecks")

    # After prechecks: early return, blockchain lookup, or continue to semantic cache.
    def _after_prechecks(state: RAGState) -> str:
        if state.get("early_answer") is not None or state.get("error_message") is not None:
            return END
        if state.get("intent") == "blockchain_lookup":
            return "blockchain_lookup"
        return "semantic_cache"

    graph.add_conditional_edges(
        "prechecks", _after_prechecks,
        {END: END, "blockchain_lookup": "blockchain_lookup", "semantic_cache": "semantic_cache"},
    )
    graph.add_edge("blockchain_lookup", END)

    # If semantic cache hit, end immediately. Otherwise decompose the query.
    def _after_semantic_cache(state: RAGState) -> str:
        if state.get("early_answer") is not None or state.get("error_message") is not None:
            return END
        return "decompose"

    graph.add_conditional_edges(
        "semantic_cache", _after_semantic_cache, {END: END, "decompose": "decompose"}
    )

    graph.add_edge("decompose", "retrieve")

    # If retrieval yields no published sources, end (caller will surface NO_KB_MATCH or error).
    def _after_retrieve(state: RAGState) -> str:
        if state.get("error_message") is not None:
            return END
        return "resolve_parents"

    graph.add_conditional_edges("retrieve", _after_retrieve, {END: END, "resolve_parents": "resolve_parents"})

    graph.add_edge("resolve_parents", "spend_limit")
    graph.add_edge("spend_limit", END)

    return graph.compile()


