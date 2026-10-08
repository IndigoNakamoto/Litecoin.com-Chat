"""
Turn knowledge-gap candidates, request logs, and thumbs-down feedback into a
review packet for the golden set.

Pure functions only. `scripts/harvest_golden_candidates.py` reads Mongo and
calls `build_packet`. Nothing here writes the golden YAML or the database.

A row is dropped when its normalized question is already a golden query, when
it is shorter than four words, when it is a follow-up (`chat_history_length`
> 0), or when it is a cache hit. Close-but-not-exact questions stay in the
packet with `close_golden_id` set.

`GOLDEN_QUESTION_CAP` matches the ceiling asserted in
`backend/tests/test_eval_scaffold.py`. Raising that assert is a separate,
explicit edit when an approved batch would pass the cap.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.utils.litecoin_vocabulary import is_litecoin_related

GOLDEN_QUESTION_CAP = 90
MIN_QUESTION_WORDS = 4
ANSWER_EXCERPT_CHARS = 240
CLOSE_JACCARD = 0.6
CLOSE_MIN_SHARED = 3

_STOP = frozenset(
    "a an the of to for in on is are was were be been being what how do does did "
    "who when where why which can could should would i my your me you we with from "
    "about and or if it this that there their".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize_query(text: str) -> str:
    """Lowercase, collapse whitespace, and strip trailing punctuation."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    return cleaned.strip(" ?!.,;:\"'`")


def slots_remaining(golden_count: int, cap: int = GOLDEN_QUESTION_CAP) -> int:
    return max(0, cap - int(golden_count))


def _content_tokens(text: str) -> set:
    return {w for w in _TOKEN.findall(normalize_query(text)) if w not in _STOP and len(w) > 2}


def _word_count(text: str) -> int:
    normalized = normalize_query(text)
    return len(normalized.split()) if normalized else 0


def citation_needle(slug: Optional[str], title: Optional[str]) -> List[str]:
    """One substring the runner can find in a chip slug or title."""
    slug_l = (slug or "").strip().lower()
    if slug_l:
        return [slug_l]
    words = [w for w in _TOKEN.findall((title or "").lower()) if len(w) >= 4 and w not in _STOP]
    if not words:
        return []
    return [max(words, key=len)]


def _cache_behavior(cache_type: Optional[str]) -> Optional[str]:
    ct = (cache_type or "").strip().lower()
    if ct == "intent_refuse" or ct.startswith("intent_refuse"):
        return "refuse"
    if ct == "intent_escalate" or ct.startswith("intent_escalate"):
        return "escalate"
    if ct == "blockchain_lookup" or ct.startswith("blockchain_lookup"):
        return "lookup"
    return None


def _on_topic(query: str, topic_cluster: Optional[str]) -> bool:
    if (topic_cluster or "").strip():
        return True
    return is_litecoin_related(query or "")


def _drop_reason(row: Dict[str, Any]) -> Optional[str]:
    if not normalize_query(row.get("query") or ""):
        return "empty"
    if int(row.get("chat_history_length") or 0) > 0:
        return "follow_up"
    if row.get("source") == "log" and row.get("cache_hit"):
        return "cache_hit"
    return None


def _excerpt(text: str) -> str:
    flat = re.sub(r"\s+", " ", (text or "").strip())
    if len(flat) <= ANSWER_EXCERPT_CHARS:
        return flat
    return flat[: ANSWER_EXCERPT_CHARS - 1].rstrip() + "…"


def close_golden_id(query: str, golden_questions: Sequence[Dict[str, Any]]) -> Optional[str]:
    """Id of a golden question that is the same ask in different words. Exact matches are handled separately."""
    tokens = _content_tokens(query)
    if not tokens:
        return None
    best_id: Optional[str] = None
    best = 0.0
    for item in golden_questions:
        other = _content_tokens(item.get("query") or "")
        if not other:
            continue
        inter = len(tokens & other)
        union = len(tokens | other)
        score = inter / union if union else 0.0
        smaller = min(len(tokens), len(other))
        if inter == smaller and smaller >= CLOSE_MIN_SHARED:
            score = max(score, CLOSE_JACCARD)
        if score > best:
            best = score
            best_id = str(item.get("id") or "") or None
    if best >= CLOSE_JACCARD:
        return best_id
    return None


def _id_prefix(behavior: str, substrings: Sequence[str]) -> str:
    if behavior == "needs_review":
        return "review"
    if behavior == "answer" and not substrings:
        return "gap"
    if behavior == "answer":
        return "faq"
    if behavior == "lookup":
        return "lookup"
    return behavior


def propose_id(behavior: str, query: str, substrings: Sequence[str], taken: Iterable[str]) -> str:
    bits = [w for w in _TOKEN.findall(normalize_query(query)) if w not in _STOP][:4]
    stem = f"{_id_prefix(behavior, substrings)}-{'-'.join(bits) or 'question'}"
    used = set(taken)
    if stem not in used:
        return stem
    n = 2
    while f"{stem}-{n}" in used:
        n += 1
    return f"{stem}-{n}"


def _suggest_category(behavior: str, substrings: Sequence[str]) -> Optional[str]:
    if behavior == "needs_review":
        return None
    if behavior == "answer" and not substrings:
        return "abstain"
    if behavior == "answer":
        return "faq"
    if behavior == "lookup":
        return "blockchain-live"
    return behavior


def _display_query(rows: Sequence[Dict[str, Any]]) -> str:
    gaps = [r for r in rows if r.get("source") == "gap" and (r.get("query") or "").strip()]
    if gaps:
        return max(gaps, key=lambda r: int(r.get("frequency") or 1))["query"].strip()
    counts: Dict[str, int] = {}
    for row in rows:
        raw = (row.get("query") or "").strip()
        if raw:
            counts[raw] = counts.get(raw, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: (item[1], len(item[0])))[0]


def _suggest(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Behavior for one normalized question. Cache routing wins, then a published article, then an open gap."""
    for row in rows:
        routed = _cache_behavior(row.get("cache_type"))
        if routed:
            return {
                "suggested_behavior": routed,
                "expected_source_substrings": [],
                "must_not_contain": [],
                "note": "",
            }

    published = [r for r in rows if (r.get("status") or "") == "published"]
    if published:
        row = published[0]
        needle = citation_needle(row.get("article_slug"), row.get("article_title"))
        note = ""
        if not needle:
            note = "published article: set expected_source_substrings from the title or slug before writing YAML"
        return {
            "suggested_behavior": "answer",
            "expected_source_substrings": needle,
            "must_not_contain": [],
            "note": note,
        }

    on_topic = any(_on_topic(r.get("query") or "", r.get("topic_cluster")) for r in rows)
    open_gap = on_topic and any(
        r.get("source") == "gap"
        or r.get("abstained")
        or r.get("is_grounded")
        or r.get("sources_count") == 0
        for r in rows
    )
    if open_gap:
        notes = ["open Litecoin gap: add must_not_contain for the specific wrong claim before writing YAML"]
        if any(r.get("payload_article_id") for r in rows):
            notes.append("CMS draft exists; add a citation needle only after it is published")
        return {
            "suggested_behavior": "answer",
            "expected_source_substrings": [],
            "must_not_contain": [],
            "note": "; ".join(notes),
        }

    off_topic_abstain = any(
        (r.get("abstained") or r.get("sources_count") == 0 or r.get("source") == "gap")
        and not _on_topic(r.get("query") or "", r.get("topic_cluster"))
        for r in rows
    )
    if off_topic_abstain:
        return {
            "suggested_behavior": "abstain",
            "expected_source_substrings": [],
            "must_not_contain": [],
            "note": "",
        }

    reasons = [r.get("feedback_reason") for r in rows if r.get("feedback_reason")]
    note = "thumbs-down: pick a behavior before writing YAML"
    if reasons:
        note = f"{note} ({reasons[0]})"
    return {
        "suggested_behavior": "needs_review",
        "expected_source_substrings": [],
        "must_not_contain": [],
        "note": note,
    }


def _frequency(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    gap = max((int(r.get("frequency") or 1) for r in rows if r.get("source") == "gap"), default=0)
    log = sum(1 for r in rows if r.get("source") == "log")
    feedback = sum(1 for r in rows if r.get("source") == "feedback")
    return {"gap": gap, "log": log, "feedback": feedback}


def _yaml_ready(suggestion: Dict[str, Any]) -> bool:
    behavior = suggestion["suggested_behavior"]
    if behavior not in {"answer", "lookup", "refuse", "escalate", "abstain"}:
        return False
    if behavior == "answer" and not suggestion["expected_source_substrings"]:
        return False
    if suggestion["note"]:
        return False
    return True


def observation_from_gap(doc: Dict[str, Any]) -> Dict[str, Any]:
    """One knowledge-candidate document, without its embedding."""
    article_id = doc.get("payload_article_id")
    return {
        "source": "gap",
        "query": doc.get("user_question") or "",
        "frequency": int(doc.get("question_frequency") or 1),
        "status": doc.get("status"),
        "payload_article_id": str(article_id) if article_id else None,
        "topic_cluster": doc.get("topic_cluster"),
        "answer_excerpt": doc.get("generated_answer") or "",
        "article_slug": doc.get("article_slug"),
        "article_title": doc.get("article_title"),
        "chat_history_length": 0,
    }


def observation_from_log(doc: Dict[str, Any]) -> Dict[str, Any]:
    """One request-log document. The caller already skipped cache hits and follow-ups, but the fields are kept so `build_packet` can drop them."""
    return {
        "source": "log",
        "query": doc.get("user_question") or "",
        "frequency": 1,
        "chat_history_length": int(doc.get("chat_history_length") or 0),
        "cache_hit": bool(doc.get("cache_hit")),
        "cache_type": doc.get("cache_type"),
        "abstained": bool(doc.get("abstained")),
        "is_grounded": bool(doc.get("is_grounded")),
        "sources_count": doc.get("sources_count"),
        "answer_excerpt": doc.get("assistant_response") or "",
    }


def observation_from_feedback(doc: Dict[str, Any]) -> Dict[str, Any]:
    """One thumbs-down document. Questions with no stored text are dropped later as empty."""
    return {
        "source": "feedback",
        "query": doc.get("user_question") or "",
        "frequency": 1,
        "feedback_reason": doc.get("reason"),
        "chat_history_length": 0,
    }


def build_packet(
    rows: Sequence[Dict[str, Any]],
    golden_questions: Sequence[Dict[str, Any]],
    cap: int = GOLDEN_QUESTION_CAP,
) -> Dict[str, Any]:
    """Group observations into review candidates. Drops exact covers, short questions, follow-ups, and cache hits."""
    golden_norm = {normalize_query(q.get("query") or ""): q for q in golden_questions if q.get("query")}
    taken_ids = {str(q.get("id")) for q in golden_questions if q.get("id")}
    dropped = {"exact_cover": 0, "too_short": 0, "follow_up": 0, "cache_hit": 0, "empty": 0}

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        reason = _drop_reason(row)
        if reason:
            dropped[reason] += 1
            continue
        key = normalize_query(row.get("query") or "")
        if key in golden_norm:
            dropped["exact_cover"] += 1
            continue
        if _word_count(key) < MIN_QUESTION_WORDS:
            dropped["too_short"] += 1
            continue
        grouped.setdefault(key, []).append(row)

    candidates: List[Dict[str, Any]] = []
    for key, group in grouped.items():
        suggestion = _suggest(group)
        query = _display_query(group)
        counts = _frequency(group)
        substrings = list(suggestion["expected_source_substrings"])
        proposed = propose_id(suggestion["suggested_behavior"], query, substrings, taken_ids)
        taken_ids.add(proposed)
        excerpts = [_excerpt(r.get("answer_excerpt") or "") for r in group if (r.get("answer_excerpt") or "").strip()]
        topics = [r.get("topic_cluster") for r in group if r.get("topic_cluster")]
        sources = []
        for name in ("gap", "log", "feedback"):
            if counts[name]:
                sources.append(name)
        candidates.append(
            {
                "proposed_id": proposed,
                "query": query,
                "sources": sources,
                "frequency": max(counts.values()) if counts else 0,
                "counts": counts,
                "suggested_behavior": suggestion["suggested_behavior"],
                "category": _suggest_category(suggestion["suggested_behavior"], substrings),
                "expected_source_substrings": substrings,
                "must_not_contain": list(suggestion["must_not_contain"]),
                "close_golden_id": close_golden_id(key, golden_questions),
                "note": suggestion["note"],
                "yaml_ready": _yaml_ready(suggestion),
                "answer_excerpt": excerpts[0] if excerpts else "",
                "topic_cluster": topics[0] if topics else None,
            }
        )

    candidates.sort(key=lambda c: (-int(c["frequency"]), c["query"].lower()))
    golden_count = len(golden_questions)
    return {
        "golden_count": golden_count,
        "cap": cap,
        "slots_remaining": slots_remaining(golden_count, cap),
        "dropped": dropped,
        "candidates": candidates,
    }
