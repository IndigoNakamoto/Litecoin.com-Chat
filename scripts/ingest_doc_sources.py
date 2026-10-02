#!/usr/bin/env python3
"""
Refresh reference-doc drafts from the source registry (backend/data_ingestion/doc_sources.yaml).

Dry-run (default) fetches and reports; --apply upserts Payload CMS drafts by sourceUrl.
Editors still publish. The same code runs weekly via the ARQ `ingest_doc_sources` cron.

    python scripts/ingest_doc_sources.py --dry-run
    python scripts/ingest_doc_sources.py --apply
    python scripts/ingest_doc_sources.py --apply --only litecoin_core_release_notes litecoin_lips_mweb
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

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

from backend.data_ingestion.doc_sources import format_reports, run_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest reference docs from the source registry into Payload drafts.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch and report only (default).")
    mode.add_argument("--apply", action="store_true", help="Create/update Payload CMS drafts.")
    parser.add_argument("--only", nargs="*", help="Source ids to run (default: all enabled).")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    reports = asyncio.run(run_all(apply=bool(args.apply), only=args.only))
    print(format_reports(reports, apply=bool(args.apply)))
    return 1 if any(r.errors for r in reports) and not reports else 0


if __name__ == "__main__":
    raise SystemExit(main())
