#!/usr/bin/env python3
"""
Read-only harvest of golden-set candidates.

Prints a JSON review packet to stdout. Does not write Mongo or
`backend/tests/eval/golden_questions.yaml`. If Mongo is unreachable, exits
1 and does not invent candidates.

    python scripts/harvest_golden_candidates.py
    python scripts/harvest_golden_candidates.py --days 30 --limit 200

Connection: `MONGO_DETAILS` or `MONGO_URI`, same fallback as
`backend/dependencies.py`. Env files are loaded only to fill those variables
when they are not already set: `.env.docker.prod`, `.env.secrets`,
`backend/.env`, `.env`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for env_path in (ROOT / ".env.docker.prod", ROOT / ".env.secrets", ROOT / "backend" / ".env", ROOT / ".env"):
    load_dotenv(env_path)

from backend.eval.golden_harvest import (  # noqa: E402
    build_packet,
    observation_from_feedback,
    observation_from_gap,
    observation_from_log,
)
from backend.eval.golden_runner import load_golden_questions  # noqa: E402


def _mongo_uri() -> str:
    return (os.getenv("MONGO_DETAILS") or os.getenv("MONGO_URI") or "").strip()


def _safe_error(exc: BaseException, uri: str) -> str:
    text = str(exc)
    if uri and uri in text:
        text = text.replace(uri, "mongodb://…")
    return text


def _article_hints(db: Any, payload_ids: List[str]) -> Dict[str, Dict[str, str]]:
    if not payload_ids:
        return {}
    name = os.getenv("MONGO_COLLECTION_NAME", "litecoin_docs")
    found: Dict[str, Dict[str, str]] = {}
    try:
        cursor = db[name].find(
            {"metadata.payload_id": {"$in": payload_ids}},
            {"metadata.payload_id": 1, "metadata.slug": 1, "metadata.doc_title": 1, "metadata.title": 1},
        )
        for doc in cursor:
            md = doc.get("metadata") or {}
            pid = str(md.get("payload_id") or "")
            if not pid or pid in found:
                continue
            found[pid] = {
                "article_slug": md.get("slug") or "",
                "article_title": md.get("doc_title") or md.get("title") or "",
            }
    except Exception as exc:  # noqa: BLE001
        print(f"article lookup skipped: {exc}", file=sys.stderr)
    return found


def _collect(db: Any, days: int, limit: int) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    rows: List[Dict[str, Any]] = []

    gap_name = os.getenv("KNOWLEDGE_CANDIDATES_COLLECTION_NAME", "knowledge_candidates")
    gaps = list(
        db[gap_name]
        .find(
            {"status": {"$in": ["pending", "approved", "published"]}},
            {"question_embedding": 0},
        )
        .sort("question_frequency", -1)
        .limit(limit)
    )
    published_ids = [
        str(doc["payload_article_id"])
        for doc in gaps
        if doc.get("status") == "published" and doc.get("payload_article_id")
    ]
    hints = _article_hints(db, published_ids)
    for doc in gaps:
        if doc.get("status") == "published":
            hint = hints.get(str(doc.get("payload_article_id") or ""))
            if hint:
                doc = {**doc, **hint}
        rows.append(observation_from_gap(doc))

    log_name = os.getenv("LLM_REQUEST_LOGS_COLLECTION_NAME", "llm_request_logs")
    # First-turn, non-cache rows only, so `--limit` is not spent on replays.
    # `$in: [0, None]` also matches documents that never stored the field.
    log_filter = {
        "timestamp": {"$gte": cutoff},
        "chat_history_length": {"$in": [0, None]},
        "cache_hit": {"$ne": True},
        "$or": [
            {"abstained": True},
            {"is_grounded": True},
            {"sources_count": 0},
        ],
    }
    for doc in db[log_name].find(log_filter, {"question_embedding": 0}).sort("timestamp", -1).limit(limit):
        rows.append(observation_from_log(doc))

    feedback_name = os.getenv("ANSWER_FEEDBACK_COLLECTION_NAME", "answer_feedback")
    feedback_filter = {
        "verdict": "down",
        "timestamp": {"$gte": cutoff},
        "user_question": {"$exists": True, "$nin": [None, ""]},
    }
    for doc in db[feedback_name].find(feedback_filter).sort("timestamp", -1).limit(limit):
        rows.append(observation_from_feedback(doc))
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Print a golden-set review packet as JSON. Read-only.")
    parser.add_argument("--days", type=int, default=30, help="How far back to read logs and thumbs-down feedback (default 30).")
    parser.add_argument("--limit", type=int, default=200, help="Max documents to read from each collection (default 200).")
    args = parser.parse_args(argv)

    uri = _mongo_uri()
    if not uri:
        print("MONGO_DETAILS or MONGO_URI is not set. No candidates were invented.", file=sys.stderr)
        return 1

    db_name = os.getenv("MONGO_DATABASE_NAME") or os.getenv("MONGO_DB_NAME") or "litecoin_rag_db"
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    except Exception as exc:  # noqa: BLE001
        print(f"Mongo is unreachable: {_safe_error(exc, uri)}", file=sys.stderr)
        print("No candidates were invented.", file=sys.stderr)
        return 1

    try:
        try:
            client.admin.command("ping")
            rows = _collect(client[db_name], days=args.days, limit=max(1, args.limit))
            packet = build_packet(rows, load_golden_questions())
        except PyMongoError as exc:
            print(f"Mongo is unreachable: {_safe_error(exc, uri)}", file=sys.stderr)
            print("No candidates were invented.", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"Harvest failed: {_safe_error(exc, uri)}", file=sys.stderr)
            print("No candidates were invented.", file=sys.stderr)
            return 1
    finally:
        client.close()

    json.dump(packet, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
