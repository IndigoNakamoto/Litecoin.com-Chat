"""Golden-set eval against a live pipeline.

Skipped unless EVAL_RETRIEVAL=1 against a populated index. Default CI uses -m "not eval".
The nightly ARQ job `run_golden_eval` runs the same runner and alerts on Discord.

Two checks:
- retrieval hit: every `answer` question with expected substrings hits the KB (fast, retrieve node only)
- full behavior: the whole pipeline produces the expected behavior (answer/lookup/refuse/escalate/abstain)
  with citations where required
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.eval.golden_runner import load_golden_questions, run_golden_eval

GOLDEN_PATH = Path(__file__).with_name("golden_questions.yaml")


def _enabled() -> bool:
    return os.getenv("EVAL_RETRIEVAL", "").lower() in ("1", "true", "yes")


@pytest.mark.eval
@pytest.mark.asyncio
async def test_golden_questions_retrieval_hit():
    if not _enabled():
        pytest.skip("Set EVAL_RETRIEVAL=1 against a populated FAISS/Mongo index")

    from backend.rag_pipeline import RAGPipeline
    from backend.rag_graph.nodes.retrieve import make_retrieve_node

    questions = [q for q in load_golden_questions(GOLDEN_PATH) if q.get("expected_behavior") == "answer" and q.get("expected_source_substrings")]
    assert questions, "golden set has no retrieval-hit questions"

    pipeline = RAGPipeline()
    node = make_retrieve_node(pipeline)
    misses = []

    for item in questions:
        needles = [s.lower() for s in item["expected_source_substrings"]]
        state = await node({"retrieval_query": item["query"], "metadata": {}})
        docs = state.get("published_sources") or state.get("context_docs") or []
        blob = " ".join(
            f"{d.page_content} {d.metadata.get('doc_title', '')} {d.metadata.get('slug', '')}" for d in docs
        ).lower()
        if not any(n in blob for n in needles):
            misses.append(item["id"])

    assert not misses, f"retrieval miss for golden ids: {misses}"


@pytest.mark.eval
@pytest.mark.asyncio
async def test_golden_questions_full_behavior():
    if not _enabled():
        pytest.skip("Set EVAL_RETRIEVAL=1 against a populated FAISS/Mongo index")

    from backend.rag_pipeline import RAGPipeline

    report = await run_golden_eval(RAGPipeline(), run_id="pytest", questions=load_golden_questions(GOLDEN_PATH))
    failing = [f"{r.id}: expected {r.expected_behavior}, got {r.actual_behavior} ({r.note})" for r in report.results if not r.passed]
    assert not report.behavior_failures, "behavior failures:\n" + "\n".join(failing)
    assert not report.citation_misses, "citation misses:\n" + "\n".join(failing)
