#!/usr/bin/env python3
"""
Seed editor-authored articles from content/articles/**/*.md into Payload CMS as drafts.

Dry-run (default) parses and lists the files; --apply upserts drafts by exact title.
Existing articles keep their status (published stays published) and unchanged ones
are skipped, like the weekly reference-doc import. Editors still publish in the CMS.

    python scripts/seed_articles.py --dry-run
    python scripts/seed_articles.py --apply
    python scripts/seed_articles.py --apply --only ordinals-lite-faq litecoin-space-basics
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

from backend.data_ingestion.authored_articles import (  # noqa: E402
    CONTENT_DIR,
    AuthoredArticleError,
    format_seed_report,
    load_articles,
    seed_articles,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed content/articles/**/*.md into Payload CMS drafts.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Parse and list only (default).")
    mode.add_argument("--apply", action="store_true", help="Create/update Payload CMS drafts.")
    parser.add_argument("--only", nargs="*", help="File stems to seed (default: all).")
    parser.add_argument("--dir", type=Path, default=CONTENT_DIR, help=f"Content directory (default {CONTENT_DIR}).")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        articles = load_articles(args.dir, only=args.only)
    except AuthoredArticleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    report = asyncio.run(seed_articles(articles, apply=bool(args.apply)))
    print(format_seed_report(articles, report, apply=bool(args.apply)))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
