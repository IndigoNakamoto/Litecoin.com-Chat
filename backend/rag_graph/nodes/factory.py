from __future__ import annotations

from typing import Any, Callable, Dict

from .sanitize_normalize import make_sanitize_normalize_node
from .route import make_route_node
from .prechecks import make_prechecks_node
from .semantic_cache import make_semantic_cache_node
from .decompose import make_decompose_node
from .retrieve import make_retrieve_node
from .resolve_parents import make_resolve_parents_node
from .spend_limit import make_spend_limit_node


def build_nodes(pipeline: Any) -> Dict[str, Callable[..., Any]]:
    """
    Bind node callables to a concrete `RAGPipeline` instance.

    We keep the pipeline type as `Any` to avoid a hard import dependency on
    `backend.rag_pipeline`, which would create circular imports.
    """
    return {
        "sanitize_normalize": make_sanitize_normalize_node(pipeline),
        "route": make_route_node(pipeline),
        "prechecks": make_prechecks_node(pipeline),
        "semantic_cache": make_semantic_cache_node(pipeline),
        "decompose": make_decompose_node(pipeline),
        "retrieve": make_retrieve_node(pipeline),
        "resolve_parents": make_resolve_parents_node(pipeline),
        "spend_limit": make_spend_limit_node(pipeline),
    }


