"""CI-safe checks that the eval golden set exists and is well-formed."""

from pathlib import Path

import yaml

GOLDEN_PATH = Path(__file__).resolve().parent / "eval" / "golden_questions.yaml"
REQUIRED_CATEGORIES = {"faq", "conceptual", "blockchain-live", "adversarial", "refuse", "escalate", "abstain", "orient"}
VALID_BEHAVIORS = {"answer", "lookup", "refuse", "escalate", "abstain"}


def test_golden_questions_yaml_schema():
    data = yaml.safe_load(GOLDEN_PATH.read_text())
    questions = data.get("questions") or []
    # Spec: a 50-80 question set covering basics, MWEB, supply, a known scam, a live tx, an out-of-scope price bet.
    assert 50 <= len(questions) <= 80

    ids = []
    categories = set()
    behaviors = set()
    for item in questions:
        assert item.get("id")
        assert item.get("query")
        assert item.get("category") in REQUIRED_CATEGORIES
        assert item.get("expected_behavior") in VALID_BEHAVIORS
        assert isinstance(item.get("expected_source_substrings"), list)
        if item["expected_behavior"] != "answer":
            assert item["expected_source_substrings"] == [], item["id"]
        ids.append(item["id"])
        categories.add(item["category"])
        behaviors.add(item["expected_behavior"])

    assert len(ids) == len(set(ids))
    assert REQUIRED_CATEGORIES <= categories
    assert behaviors == VALID_BEHAVIORS
    assert any(q["expected_source_substrings"] for q in questions)
    # Every refuse question is answered without touching the knowledge base.
    assert sum(1 for q in questions if q["expected_behavior"] == "refuse") >= 8
    assert sum(1 for q in questions if q["expected_behavior"] == "lookup") >= 5


def test_golden_runner_scoring_logic():
    from langchain_core.documents import Document

    from backend.eval.golden_runner import classify_actual_behavior, score_question

    pub = [Document(page_content="MWEB is MimbleWimble Extension Blocks", metadata={"status": "published", "doc_title": "MWEB"})]

    # answer + citation hit
    r = score_question({"id": "a", "query": "q", "expected_behavior": "answer", "expected_source_substrings": ["mimblewimble"]}, "ans", pub, {}, 10)
    assert r.passed and r.citation_ok and r.behavior_ok

    # answer but citation miss
    r = score_question({"id": "b", "query": "q", "expected_behavior": "answer", "expected_source_substrings": ["halving"]}, "ans", pub, {}, 10)
    assert r.behavior_ok and not r.citation_ok and not r.passed

    # answer with required citation but no sources at all
    r = score_question({"id": "c", "query": "q", "expected_behavior": "answer", "expected_source_substrings": [], "requires_citation": True}, "ans", [], {}, 10)
    assert not r.citation_ok
    # known-gap answer (web tier): no substrings, no citation required, guards only
    r = score_question({"id": "c2", "query": "q", "expected_behavior": "answer", "expected_source_substrings": [], "must_not_contain": ["staking rewards are paid"]}, "Litecoin has no staking.", [], {"is_grounded": True}, 10)
    assert r.passed

    # abstain detection from metadata or canonical text
    assert classify_actual_behavior("x", [], {"abstained": True}) == "abstain"
    assert classify_actual_behavior("The knowledge base does not cover this yet.", [], {}) == "abstain"
    assert classify_actual_behavior("x", [], {"intent": "refuse"}) == "refuse"
    assert classify_actual_behavior("x", [], {"cache_type": "intent_escalate"}) == "escalate"
    assert classify_actual_behavior("x", [], {"cache_type": "blockchain_lookup"}) == "lookup"
    assert classify_actual_behavior("x", pub, {}) == "answer"

    # refuse question answered instead -> behavior failure
    r = score_question({"id": "d", "query": "q", "expected_behavior": "refuse", "expected_source_substrings": []}, "Sure, buy now", pub, {}, 10)
    assert not r.behavior_ok and not r.passed

    # forbidden phrase
    r = score_question(
        {"id": "e", "query": "q", "expected_behavior": "refuse", "expected_source_substrings": [], "must_not_contain": ["enter your seed"]},
        "I won't help. Enter your seed here.",
        [],
        {"intent": "refuse"},
        10,
    )
    assert not r.behavior_ok


def test_golden_runner_regression_diff():
    import asyncio

    from backend.eval.golden_runner import run_golden_eval

    class _P:
        async def aquery(self, q, _h):
            if "buy" in q:
                return "no advice", [], {"intent": "refuse"}
            if "price" in q:
                return "$1", [], {"cache_type": "blockchain_lookup"}
            return "the answer", [], {}  # no sources -> citation miss

    qs = [
        {"id": "r1", "query": "should I buy", "expected_behavior": "refuse", "expected_source_substrings": []},
        {"id": "l1", "query": "ltc price", "expected_behavior": "lookup", "expected_source_substrings": []},
        {"id": "a1", "query": "what is mweb", "expected_behavior": "answer", "expected_source_substrings": ["mweb"]},
    ]
    report = asyncio.run(run_golden_eval(_P(), run_id="t", previous_per_question={"a1": True, "r1": False}, questions=qs))
    assert report.total == 3 and report.passed == 2
    assert report.citation_misses == ["a1"]
    assert report.regressions == ["a1"]
    assert report.fixed == ["r1"]
    assert report.should_alert
    assert report.summary()["per_question"] == {"r1": True, "l1": True, "a1": False}
