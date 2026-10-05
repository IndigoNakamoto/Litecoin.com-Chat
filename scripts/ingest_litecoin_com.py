#!/usr/bin/env python3
"""
Ingest litecoin.com Learning Center pages as Payload CMS drafts.

Dry-run (default) discovers and extracts pages without writing to the CMS.
--apply creates draft articles. An admin must publish them before they
enter the RAG vector store.

Usage (from repo root):

    python scripts/ingest_litecoin_com.py --dry-run
    python scripts/ingest_litecoin_com.py --apply
    python scripts/ingest_litecoin_com.py --section projects --dry-run

Note: this CLI always writes drafts (status reset on re-run). The weekly
registry run (`scripts/ingest_doc_sources.py`) is the status-preserving path.
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

# Host-side runs cannot reach the docker service name.
_payload_url = os.getenv("PAYLOAD_URL") or ""
if not _payload_url or "payload_cms" in _payload_url:
    os.environ["PAYLOAD_URL"] = "http://localhost:3001"

from backend.data_ingestion.litecoin_com_scraper import (  # noqa: E402
    DEFAULT_REQUEST_DELAY_SECONDS,
    MIN_WORD_COUNT,
    SECTION_LEARNING_CENTER,
    SECTIONS,
    format_report,
    run_ingest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape litecoin.com Learning Center pages into Payload drafts.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and extract only (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Create Payload CMS draft articles.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY_SECONDS,
        help=f"Seconds between HTTP requests (default {DEFAULT_REQUEST_DELAY_SECONDS}).",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=MIN_WORD_COUNT,
        help=f"Skip pages with fewer than this many body words (default {MIN_WORD_COUNT}).",
    )
    parser.add_argument(
        "--section",
        choices=SECTIONS,
        default=SECTION_LEARNING_CENTER,
        help="Site section to import: Learning Center articles (default) or /projects listings.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    apply = bool(args.apply)
    report = asyncio.run(
        run_ingest(
            apply=apply,
            delay_seconds=args.delay,
            min_words=args.min_words,
            section=args.section,
        )
    )
    print(format_report(report, apply=apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
