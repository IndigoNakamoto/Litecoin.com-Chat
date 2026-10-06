# Milestone 13: Implement Developer Documentation & Resources

## Description
This milestone focuses on providing quick access to snippets from Litecoin developer documentation and technical resources.

## Key Tasks
*   Ingest relevant Litecoin developer documentation into the RAG system.
*   Optimize embedding and retrieval for technical content, including code snippets.
*   Refine the RAG pipeline to accurately answer developer-centric queries.

## Status
In Progress

Done so far:
*   Source registry (`backend/data_ingestion/doc_sources.yaml`, weekly ARQ cron `ingest_doc_sources`) imports Litecoin Core docs and release notes, MWEB LIPs, the litecoin.com Learning Center and `/projects` listings, the Litecoin Dev Kit repos (BDK port and siblings), Ordinals Lite and Litecoin Space READMEs and the LitVM blog as Payload drafts tagged with `sourceTier`, `reviewIntervalDays` and a category. Re-runs preserve the article's status and skip unchanged content.
*   Editor-authored drafts from `content/articles/` via `scripts/seed_articles.py` (Ordinals explainers adapted to Litecoin, Litecoin Space FAQ snapshots and REST API overview).
*   Published 2026-10-05: 75 articles / 2,071 chunks; "Build on Litecoin" and "Ordinals & Digital Artifacts" landing topics with screened questions; vocabulary and golden-set entries for LDK, Ordinals Lite, Litecoin Space, lit/vB.

Remaining:
*   The disabled/thin registry entries (Litecoin Space API reference is an SPA and yields nothing; `/projects` hub text such as donation matching is not stored as its own article).
*   Retrieval tuning for code snippets and RPC/CLI examples; the acceptance criterion "accurate code snippets" is not yet measured by the golden set.

## Dependencies
*   Completed: Milestone 12 (Implement Market Data & Insights)

## Acceptance Criteria
*   Users can successfully query for Litecoin developer documentation and resources.
*   The system provides accurate code snippets and relevant links.
*   Technical questions are answered clearly and concisely.
