"""CI-safe checks that the eval golden set exists and is well-formed."""

from pathlib import Path

import yaml

GOLDEN_PATH = Path(__file__).resolve().parent / "eval" / "golden_questions.yaml"
REQUIRED_CATEGORIES = {"faq", "conceptual", "blockchain-live", "adversarial"}


def test_golden_questions_yaml_schema():
    data = yaml.safe_load(GOLDEN_PATH.read_text())
    questions = data.get("questions") or []
    assert 10 <= len(questions) <= 20

    ids = []
    categories = set()
    for item in questions:
        assert item.get("id")
        assert item.get("query")
        assert item.get("category") in REQUIRED_CATEGORIES
        assert isinstance(item.get("expected_source_substrings"), list)
        ids.append(item["id"])
        categories.add(item["category"])

    assert len(ids) == len(set(ids))
    assert REQUIRED_CATEGORIES <= categories
    assert any(q["expected_source_substrings"] for q in questions)
