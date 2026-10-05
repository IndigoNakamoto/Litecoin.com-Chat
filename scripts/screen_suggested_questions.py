#!/usr/bin/env python3
"""
Screen suggested questions against the running backend before activating them.

For each question the script runs the public chat endpoint (fingerprint challenge
+ SSE stream, exactly like the frontend) and classifies the outcome:

    PASS      knowledge answer with at least one KB source chip (check the chips
              with --show-chips: a thin KB can attach unrelated articles)
    WEB_ONLY  answered only from the web tier (no KB chips)   -> keep inactive
    LIVE      routed to a live Litecoin Space / litview card  -> fine for "Live Network Data", not pre-cached
    CACHED    a replayed answer (suggested / exact / vector cache); clear the
              caches and screen again before trusting it      -> never activated
    REFUSE / ESCALATE / PIN / ABSTAIN / ERROR                 -> keep inactive

Questions come from Payload (default: inactive ones) or from --questions. With
--activate, PASS questions (and LIVE ones when --allow-live) are flipped to
isActive=true in Payload; nothing else is written.

    python scripts/screen_suggested_questions.py                     # screen inactive questions
    python scripts/screen_suggested_questions.py --all               # screen every question
    python scripts/screen_suggested_questions.py --activate          # activate PASS
    python scripts/screen_suggested_questions.py --questions "What is a litoshi?"

Backend: BACKEND_URL (default http://localhost:8000). Payload: PAYLOAD_URL +
PAYLOAD_API_KEY (service key). Paced at ~7 s/question to stay inside the
challenge rate limit (10/min).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env.docker.prod")
load_dotenv(ROOT / ".env.secrets")
load_dotenv(ROOT / "backend" / ".env")
load_dotenv(ROOT / ".env")

_payload_url = os.getenv("PAYLOAD_URL") or ""
if not _payload_url or "payload_cms" in _payload_url:
    os.environ["PAYLOAD_URL"] = "http://localhost:3001"

# Host-side runs cannot reach docker service names (BACKEND_URL=http://litecoin-backend:8000 in the env files).
_backend_url = (os.getenv("BACKEND_URL") or "").rstrip("/")
if not _backend_url or "://litecoin-backend" in _backend_url or "://backend" in _backend_url:
    _backend_url = "http://localhost:8000"
BACKEND_URL = _backend_url
PACE_SECONDS = float(os.getenv("SCREEN_PACE_SECONDS", "7"))


@dataclass
class Outcome:
    question: str
    verdict: str
    kb_sources: List[str] = field(default_factory=list)
    tiers: List[str] = field(default_factory=list)
    web_sources: int = 0
    early_type: Optional[str] = None
    seconds: float = 0.0
    answer_preview: str = ""
    error: Optional[str] = None
    payload_id: Optional[str] = None
    category: Optional[str] = None


async def _challenge(client: httpx.AsyncClient, fp_hash: str) -> str:
    for attempt in range(6):
        r = await client.get(f"{BACKEND_URL}/api/v1/auth/challenge", headers={"X-Fingerprint": fp_hash})
        if r.status_code == 200:
            data = r.json()
            return data.get("challenge") or data["challenge_id"]
        if r.status_code == 429:
            await asyncio.sleep(10 + 5 * attempt)
            continue
        raise RuntimeError(f"challenge -> {r.status_code}: {r.text[:200]}")
    raise RuntimeError("challenge rate-limited repeatedly")


async def screen_one(client: httpx.AsyncClient, fp_hash: str, question: str) -> Outcome:
    out = Outcome(question=question, verdict="ERROR")
    t0 = time.monotonic()
    try:
        challenge_id = await _challenge(client, fp_hash)
        headers = {"X-Fingerprint": f"fp:{challenge_id}:{fp_hash}", "Content-Type": "application/json", "Accept": "text/event-stream"}
        body = {"query": question, "chat_history": []}
        text_parts: List[str] = []
        live = False
        async with client.stream("POST", f"{BACKEND_URL}/api/v1/chat/stream", json=body, headers=headers) as resp:
            if resp.status_code != 200:
                out.error = f"stream -> {resp.status_code}: {(await resp.aread())[:200]!r}"
                return out
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                status = ev.get("status")
                if status == "streaming":
                    text_parts.append(ev.get("chunk") or "")
                elif status == "sources":
                    for chip in ev.get("sources") or []:
                        out.kb_sources.append(str(chip.get("title") or chip.get("payload_id") or "?"))
                        out.tiers.append(str(chip.get("tier") or "?"))
                elif status == "blockchain_data":
                    live = True
                elif status == "error":
                    out.error = ev.get("error") or "stream error"
                elif status == "complete":
                    out.early_type = ev.get("earlyType")
                    out.web_sources = len(ev.get("webSources") or [])
                    abstained = bool(ev.get("abstained"))
                    et = out.early_type or ""
                    from_cache = ev.get("fromCache")
                    if from_cache or et in ("exact_redis", "redis_vector", "semantic", "exact"):
                        # A replayed answer says nothing about today's KB; clear the
                        # caches (admin cache/response/clear) and screen again.
                        out.verdict = "CACHED"
                    elif ev.get("incidentPinId") or et == "incident_pin":
                        out.verdict = "PIN"
                    elif et == "intent_refuse":
                        out.verdict = "REFUSE"
                    elif et == "intent_escalate":
                        out.verdict = "ESCALATE"
                    elif live or et.startswith("blockchain_lookup"):
                        out.verdict = "LIVE"
                    elif abstained:
                        out.verdict = "ABSTAIN"
                    elif out.kb_sources:
                        out.verdict = "PASS"
                    elif out.web_sources:
                        out.verdict = "WEB_ONLY"
                    else:
                        out.verdict = "NO_SOURCES"
        out.answer_preview = "".join(text_parts).strip().replace("\n", " ")[:110]
        if out.error and out.verdict == "ERROR":
            pass
    except Exception as e:  # noqa: BLE001
        out.error = str(e)
    out.seconds = time.monotonic() - t0
    return out


async def payload_questions(client: httpx.AsyncClient, include_active: bool) -> List[Dict[str, Any]]:
    from backend.services.article_draft_generator import _get_payload_url, _payload_headers

    params: Dict[str, Any] = {"limit": 500, "depth": 1, "sort": "order"}
    if not include_active:
        params["where[isActive][equals]"] = "false"
    r = await client.get(f"{_get_payload_url()}/api/suggested-questions", params=params, headers=_payload_headers())
    r.raise_for_status()
    docs = r.json().get("docs") or []
    out = []
    for d in docs:
        cat = d.get("category")
        out.append({"id": d["id"], "question": d["question"], "isActive": d.get("isActive"),
                    "category": (cat or {}).get("name") if isinstance(cat, dict) else cat})
    return out


async def activate(client: httpx.AsyncClient, ids: List[str]) -> int:
    from backend.services.article_draft_generator import _get_payload_url, _payload_headers

    n = 0
    for qid in ids:
        r = await client.patch(f"{_get_payload_url()}/api/suggested-questions/{qid}", json={"isActive": True}, headers=_payload_headers())
        if r.status_code in (200, 201):
            n += 1
        else:
            print(f"  ! activate {qid} -> {r.status_code}: {r.text[:200]}")
    return n


async def main_async(args: argparse.Namespace) -> int:
    fp_hash = secrets.token_hex(16)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        if args.questions:
            items = [{"id": None, "question": q, "category": None} for q in args.questions]
        else:
            items = await payload_questions(client, include_active=args.all)
        if not items:
            print("nothing to screen")
            return 0
        print(f"screening {len(items)} question(s) against {BACKEND_URL} (pace {PACE_SECONDS:.0f}s)\n")
        outcomes: List[Outcome] = []
        for i, it in enumerate(items):
            o = await screen_one(client, fp_hash, it["question"])
            o.payload_id, o.category = it.get("id"), it.get("category")
            outcomes.append(o)
            src = ", ".join(sorted(set(o.tiers))) if o.tiers else "-"
            extra = f" err={o.error}" if o.error else ""
            print(f"{o.verdict:10} kb={len(o.kb_sources):<2} web={o.web_sources:<2} tiers={src:12} {o.seconds:5.1f}s  [{o.category or '-'}] {o.question}{extra}")
            if args.verbose and o.answer_preview:
                print(f"           -> {o.answer_preview}")
            if args.show_chips:
                for title, tier in zip(o.kb_sources, o.tiers):
                    print(f"           chip [{tier}] {title}")
            if i < len(items) - 1:
                await asyncio.sleep(PACE_SECONDS)

        summary: Dict[str, int] = {}
        for o in outcomes:
            summary[o.verdict] = summary.get(o.verdict, 0) + 1
        print("\nsummary:", ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))

        if args.activate:
            ok = {"PASS"} | ({"LIVE"} if args.allow_live else set())
            ids = [o.payload_id for o in outcomes if o.payload_id and o.verdict in ok]
            n = await activate(client, ids)
            print(f"activated {n}/{len(ids)} question(s)")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Screen suggested questions against the backend; optionally activate the ones that pass.")
    p.add_argument("--all", action="store_true", help="Screen active questions too (default: inactive only).")
    p.add_argument("--questions", nargs="*", help="Ad-hoc question texts instead of Payload rows (never activates).")
    p.add_argument("--activate", action="store_true", help="Set isActive=true on PASS questions in Payload.")
    p.add_argument("--allow-live", action="store_true", help="Also activate LIVE (blockchain card) questions.")
    p.add_argument("-v", "--verbose", action="store_true", help="Print an answer preview per question.")
    p.add_argument("--show-chips", action="store_true", help="List the KB source chips (title + tier) behind each answer.")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
