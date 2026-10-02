"""
Golden-set runner.

Loads `backend/tests/eval/golden_questions.yaml`, runs every question through
the real pipeline (`RAGPipeline.aquery`), and scores:

- behavior   : expected `answer | abstain | refuse | escalate | lookup` vs what
               the pipeline actually did (derived from metadata / answer text)
- citation   : for `answer` questions, at least one published source was cited
               and, when `expected_source_substrings` is given, one of them
               appears in the cited titles/slugs/content
- regression : per-question pass/fail diffed against the previous stored run

Alerts (Discord) only on: citation miss, abstain/refuse failure, or a question
that passed last run and fails now. That replaces manual QA.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "golden_questions.yaml"
VALID_BEHAVIORS = ("answer", "abstain", "refuse", "escalate", "lookup")


@dataclass
class QuestionResult:
    id: str
    category: str
    query: str
    expected_behavior: str
    actual_behavior: str
    behavior_ok: bool
    citation_ok: bool
    passed: bool
    latency_ms: int
    sources: List[str] = field(default_factory=list)
    note: str = ""


@dataclass
class EvalReport:
    run_id: str
    total: int
    passed: int
    failed: int
    behavior_failures: List[str]
    citation_misses: List[str]
    regressions: List[str]
    fixed: List[str]
    results: List[QuestionResult]
    duration_s: float

    def summary(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.passed / self.total, 3) if self.total else 0.0,
            "behavior_failures": self.behavior_failures,
            "citation_misses": self.citation_misses,
            "regressions": self.regressions,
            "fixed": self.fixed,
            "per_question": {r.id: r.passed for r in self.results},
            "duration_s": round(self.duration_s, 1),
        }

    @property
    def should_alert(self) -> bool:
        return bool(self.citation_misses or self.behavior_failures or self.regressions)


def load_golden_questions(path: Path = GOLDEN_PATH) -> List[Dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    questions = data.get("questions") or []
    for q in questions:
        q.setdefault("expected_behavior", "lookup" if q.get("category") == "blockchain-live" else "answer")
        q.setdefault("expected_source_substrings", [])
    return questions


def classify_actual_behavior(answer: str, sources: Sequence[Any], metadata: Dict[str, Any]) -> str:
    """Derive what the pipeline did from its outputs."""
    intent = (metadata.get("intent") or "").lower()
    cache_type = (metadata.get("cache_type") or "").lower()
    if metadata.get("abstained") or "knowledge base does not cover" in (answer or "").lower():
        return "abstain"
    if intent == "refuse" or cache_type == "intent_refuse":
        return "refuse"
    if intent == "escalate" or cache_type == "intent_escalate":
        return "escalate"
    if intent == "blockchain_lookup" or cache_type.startswith("blockchain_lookup") or metadata.get("blockchain_entity"):
        return "lookup"
    if intent == "incident_pin":
        return "answer"
    return "answer"


def _source_blob(sources: Sequence[Any]) -> str:
    parts: List[str] = []
    for d in sources or []:
        md = getattr(d, "metadata", None) or {}
        parts.append(str(getattr(d, "page_content", "") or ""))
        parts.append(str(md.get("doc_title") or md.get("title") or ""))
        parts.append(str(md.get("slug") or ""))
    return " ".join(parts).lower()


def _source_titles(sources: Sequence[Any]) -> List[str]:
    out: List[str] = []
    for d in sources or []:
        md = getattr(d, "metadata", None) or {}
        t = md.get("doc_title") or md.get("title")
        if t and t not in out:
            out.append(str(t))
    return out


def score_question(q: Dict[str, Any], answer: str, sources: Sequence[Any], metadata: Dict[str, Any], latency_ms: int) -> QuestionResult:
    expected = q.get("expected_behavior", "answer")
    actual = classify_actual_behavior(answer, sources, metadata)
    behavior_ok = actual == expected

    citation_ok = True
    note = ""
    if expected == "answer":
        published = [d for d in sources if (getattr(d, "metadata", None) or {}).get("status") in (None, "published")]
        if not published:
            citation_ok = False
            note = "no cited sources"
        else:
            needles = [s.lower() for s in q.get("expected_source_substrings") or []]
            if needles:
                blob = _source_blob(published)
                if not any(n in blob for n in needles):
                    citation_ok = False
                    note = f"none of {needles} in cited sources"
    must_not = [s.lower() for s in q.get("must_not_contain") or []]
    if must_not and any(m in (answer or "").lower() for m in must_not):
        behavior_ok = False
        note = (note + "; " if note else "") + "answer contains forbidden phrase"

    return QuestionResult(
        id=q["id"],
        category=q.get("category", ""),
        query=q["query"],
        expected_behavior=expected,
        actual_behavior=actual,
        behavior_ok=behavior_ok,
        citation_ok=citation_ok,
        passed=behavior_ok and citation_ok,
        latency_ms=latency_ms,
        sources=_source_titles(sources)[:5],
        note=note,
    )


async def run_golden_eval(
    pipeline: Any,
    run_id: str,
    previous_per_question: Optional[Dict[str, bool]] = None,
    questions: Optional[List[Dict[str, Any]]] = None,
    limit: Optional[int] = None,
) -> EvalReport:
    """Run every golden question through `pipeline.aquery` and score it."""
    questions = questions if questions is not None else load_golden_questions()
    if limit:
        questions = questions[:limit]
    previous = previous_per_question or {}
    started = time.time()
    results: List[QuestionResult] = []

    for q in questions:
        t0 = time.time()
        try:
            answer, sources, metadata = await pipeline.aquery(q["query"], [])
        except Exception as e:  # noqa: BLE001
            logger.warning("golden eval: %s raised %s", q["id"], e)
            answer, sources, metadata = f"__error__ {e}", [], {"error": str(e)}
        latency_ms = int((time.time() - t0) * 1000)
        results.append(score_question(q, answer or "", sources or [], metadata or {}, latency_ms))

    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    behavior_failures = [r.id for r in results if not r.behavior_ok]
    citation_misses = [r.id for r in results if r.behavior_ok and not r.citation_ok]
    regressions = [r.id for r in results if not r.passed and previous.get(r.id) is True]
    fixed = [r.id for r in results if r.passed and previous.get(r.id) is False]

    return EvalReport(
        run_id=run_id,
        total=len(results),
        passed=len(passed),
        failed=len(failed),
        behavior_failures=behavior_failures,
        citation_misses=citation_misses,
        regressions=regressions,
        fixed=fixed,
        results=results,
        duration_s=time.time() - started,
    )


def report_to_dict(report: EvalReport) -> Dict[str, Any]:
    return {**report.summary(), "results": [asdict(r) for r in report.results]}


def eval_enabled() -> bool:
    return os.getenv("GOLDEN_EVAL_ENABLED", "true").lower() == "true"
