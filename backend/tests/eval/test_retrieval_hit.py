"""Retrieval-hit eval: each golden question with expected substrings must hit the KB.

Skipped unless EVAL_RETRIEVAL=1 against a populated index. Default CI uses -m "not eval".
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

GOLDEN_PATH = Path(__file__).with_name("golden_questions.yaml")


def load_golden_questions():
    data = yaml.safe_load(GOLDEN_PATH.read_text())
    return data.get("questions") or []


@pytest.mark.eval
@pytest.mark.asyncio
async def test_golden_questions_retrieval_hit():
    if os.getenv("EVAL_RETRIEVAL", "").lower() not in ("1", "true", "yes"):
        pytest.skip("Set EVAL_RETRIEVAL=1 against a populated FAISS/Mongo index")

    from backend.rag_pipeline import RAGPipeline
    from backend.rag_graph.nodes.retrieve import make_retrieve_node

    questions = [q for q in load_golden_questions() if q.get("expected_source_substrings")]
    assert questions, "golden set has no retrieval-hit questions"

    pipeline = RAGPipeline()
    node = make_retrieve_node(pipeline)
    misses = []

    for item in questions:
        query = item["query"]
        needles = [s.lower() for s in item["expected_source_substrings"]]
        state = await node({"retrieval_query": query, "metadata": {}})
        docs = state.get("published_sources") or state.get("context_docs") or []
        blob = " ".join(
            f"{d.page_content} {d.metadata.get('doc_title', '')} {d.metadata.get('slug', '')}"
            for d in docs
        ).lower()
        if not any(n in blob for n in needles):
            misses.append(item["id"])

    assert not misses, f"retrieval miss for golden ids: {misses}"
