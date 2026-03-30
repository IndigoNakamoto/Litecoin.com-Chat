# Mission Control — Litecoin Knowledge Hub

## The Heartbeat

| # | Milestone | Status | Notes |
|---|-----------|--------|-------|
| 1 | Project Initialization & Documentation Setup | Completed | Foundation laid — docs, structure, tooling |
| 2 | Basic Project Scaffold | Completed | FastAPI + Next.js skeleton, Docker Compose |
| 3 | Core RAG Pipeline Implementation | Completed | LangGraph state machine, retrieval, caching |
| 4 | Backend & Knowledge Base Completion | In Progress | Backend done; frontend UI & API integration remaining |
| 5 | Payload CMS Setup & Integration | Completed | Collections, webhooks, HMAC sync working |
| 6 | MVP Content Population & Validation | In Progress | Article authoring, content vetting |
| 7 | MVP Testing, Refinement & Deployment | Planned | Production hardening, E2E testing |
| 8 | Implement Trust and Feedback Features | In Progress | Source citations, user feedback loops; **[RECON] sprint** advances metadata-grounded synthesis |
| 9 | Implement Contextual Discovery | Completed | Follow-up questions, search grounding |
| 10 | Upgrade Retrieval Engine | Cancelled | Scope absorbed into M3 improvements |
| 11 | Transaction & Block Explorer | Completed | Litecoin Space API: tx, address, block, fees, mempool, tip, mining pools |
| 12 | Market Data & Insights | Completed | Price (5 currencies), hashrate, difficulty, adjustment progress |
| 13 | Developer Documentation & Resources | Planned | API docs, integration guides |

**Summary:** 8 completed, 3 in progress, 1 cancelled, 1 planned

## [RECON] RAG Optimization Sprint

Metadata-grounded synthesis: SOURCE headers in LLM context, `updated_at` on chunks, stricter prompt + tests.

- [x] **Task 1:** Extend `PayloadArticleMetadata` in [`backend/data_models.py`](backend/data_models.py) with `updated_at`.
- [x] **Task 2:** Map Payload `updatedAt` → chunk metadata in [`backend/data_ingestion/embedding_processor.py`](backend/data_ingestion/embedding_processor.py).
- [x] **Task 3:** Meta-aware `format_docs` in [`backend/rag_context_format.py`](backend/rag_context_format.py) (used by [`backend/rag_pipeline.py`](backend/rag_pipeline.py)); token-estimation uses the same context string as generation.
- [x] **Task 4:** Senior Technical Writer `SYSTEM_INSTRUCTION*` + grounded/non-grounded reconciliation; Cursor rule [`.cursor/rules/rag-synthesis-specialist.mdc`](.cursor/rules/rag-synthesis-specialist.mdc).

## Architecture Overview

```
PUBLIC FRONTEND (chat.lite.space/chat)     ADMIN FRONTEND (admin.lite.space)
  Next.js 15.5 / Shadcn / Tailwind          Next.js 16 / Radix / Tailwind
  Streaming chat, suggested questions        Dashboard, settings, analytics
           |                                          |
           | /api/v1/chat/stream                      | /api/v1/admin/*
           v                                          v
    ┌─────────────────── FASTAPI BACKEND (:8000) ──────────────────┐
    │                                                               │
    │  LangGraph RAG State Machine (9 nodes, 4 conditional exits)  │
    │  sanitize → route → prechecks → blockchain_lookup (live API) │
    │              → semantic_cache → decompose → retrieve         │
    │              → resolve_parents → spend_limit                 │
    │                            |                                  │
    │  RAG Pipeline (LLM generation + search grounding fallback)   │
    │                                                               │
    └──────────┬──────────────┬──────────────────┬─────────────────┘
               |              |                  |
           MongoDB         Redis            Payload CMS
         (persistence)   (cache/rate)     (content authoring)
                                          webhooks → vector sync
```

## Verification Gates

### Test Suite

- **Location:** `backend/tests/` (32 test files)
- **Last known state:** 121+ passing, 36 skipped, 30 non-blocking warnings
- **Run:** `pytest backend/tests/ -v`

### Coverage by Domain

| Domain | Test Files | Coverage |
|--------|-----------|----------|
| Security | 7 files | Strong — abuse prevention, rate limiting, webhook auth, headers |
| RAG Correctness | 7 files | Moderate — intent, FAQ, memory, graph state machine, streaming, context `format_docs` |
| Blockchain Data | 3 files | Good — API client, intent detection, graph node routing |
| Admin API | 3 files | Good — auth, settings, spend limits |
| Operations | 2 files | Partial — HTTPS redirect, spend limit integration |

### Known Gaps

- No dedicated chat API endpoint test (`test_api_chat.py`)
- No Payload sync lifecycle test (`test_sync_payload.py`)
- No frontend tests (Playwright / component)
- 21+ tests skip when local services (Ollama, Infinity, Redis Stack) unavailable
- 9 tests skip without `fakeredis`

### Definition of Done

Per `docs/testing/TEST_SUITE_IMPLEMENTATION_PLAN.md`: target 80-90% coverage, 85%+ for critical modules. All RAG, auth, rate limiting, spend limit, and webhook auth tests must pass before deployment.

## Key Files

| File | Lines | Role |
|------|-------|------|
| `backend/rag_pipeline.py` | ~1680 | RAG orchestration — the brain |
| `backend/rag_context_format.py` | ~55 | Metadata SOURCE headers for LLM context (`format_docs`) |
| `backend/rag_graph/state.py` | ~65 | Graph state definition (TypedDict) |
| `backend/rag_graph/graph.py` | ~80 | Graph wiring and conditional edges |
| `backend/rag_graph/nodes/blockchain_lookup.py` | ~360 | Live blockchain data node (Litecoin Space API) |
| `backend/services/blockchain_client.py` | ~420 | Async API client, Pydantic models, Redis caching |
| `backend/services/intent_classifier.py` | ~450 | Intent detection (greetings, FAQ, blockchain lookups) |
| `backend/data_models.py` | 250 | API Pydantic v2 models |
| `backend/main.py` | — | FastAPI app, public routes |
| `payload_cms/src/payload.config.ts` | — | CMS configuration |

## Recent Activity

| Date | Change | Milestone | Status |
|------|--------|-----------|--------|
| 2026-03-30 | Chat: user replies omit citations — `SYSTEM_INSTRUCTION*` in [`backend/rag_pipeline.py`](backend/rag_pipeline.py) no longer ask for markdown links, `## Sources`, or “Based on public sources:”; KB grounding stays internal via SOURCE headers. [`backend/main.py`](backend/main.py) no longer forwards SSE `status: "sources"` (still counts published docs for logging / follow-ups). Tests: [`backend/tests/test_chat_stream_follow_ups.py`](backend/tests/test_chat_stream_follow_ups.py) updated; `.cursor/rules/rag-synthesis-specialist.mdc` aligned. Full `pytest backend/tests/` not green in this environment (Mongo at `test:27017`, Infinity/Redis integration expectations); `test_chat_stream_follow_ups`, `test_astream_query`, `test_rag_pipeline` slice passed. | M8 | Completed |
| 2026-03-24 | Ops: `run-prod.sh --local-rag` now exports `INFINITY_URL` / `OLLAMA_URL` **before** main `docker compose up` so the backend container gets `http://infinity:7997` on x86 (was defaulting to `host.docker.internal`). `docker-compose.prod.yml` backend: `extra_hosts: host.docker.internal:host-gateway` for Linux + native Infinity. Fixes “Infinity connection error: All connection attempts failed” when flags are on but URL was wrong. **Recreate backend** after pull: `docker compose … up -d --force-recreate backend`. | M7 | Completed |
| 2026-03-23 | RAG: SOURCE headers are title+reader URL only (no dates in context); prompts ask for markdown `[Title](URL)` citations without dates; `ARTICLE_PUBLIC_BASE_URL` / `ARTICLE_PUBLIC_PATH_TEMPLATE` in `rag_context_format`. | M8 | Completed |
| 2026-03-23 | Intent: conceptual questions mentioning difficulty adjustment / hashrate (e.g. “How does the difficulty adjustment mechanism…”) route to RAG; live API kept for “next difficulty adjustment”, current difficulty, and raw hashrate stats. `IntentClassifier` + `test_blockchain_intent.py`. | M11 | Completed |
| 2026-03-23 | RAG synthesis: user-facing answers omit inline source citations (no bracketed titles, `— [Title] (date)`, or `[title] - (address)`); SOURCE headers remain for internal grounding only; `rag-synthesis-specialist.mdc` aligned. | M8 | Completed |
| 2026-03-23 | **[RECON] RAG synthesis:** `PayloadArticleMetadata.updated_at`; Payload `updatedAt` → chunk metadata in `embedding_processor`; SOURCE HEADER context via `rag_context_format.format_docs` (used by `rag_pipeline`); Senior Technical Writer + CoVe system prompts; new `.cursor/rules/rag-synthesis-specialist.mdc`; tests `test_format_docs.py`. RAG slice: `pytest backend/tests/test_rag_pipeline.py backend/tests/test_format_docs.py …` passed. | M8 / M3 | Completed |
| 2026-03-20 | Mining pools: intent for pool rankings + named-pool hashrate/share (Litecoin Space `/v1/mining/pools`, `/v1/mining/pool/:slug`); client helpers + `get_mining_network_hashrate_detail`; doc link for full REST surface | M11 | Completed |
| 2026-03-19 | Fixed blockchain API: plain-text endpoints, price endpoint path, 404 error handling, price freshness timestamps | M11/M12 | Completed |
| 2026-03-19 | Fixed intent detection: blockchain queries now fire regardless of is_dependent flag; removed static data disclaimer from system prompt | M11 | Completed |
| 2026-03-19 | Litecoin Space blockchain data integration: API client, graph node, intent detection, 7 frontend components, SSE protocol extension | M11/M12 | Completed |
| 2026-03-19 | Initialized `.cursor/rules/` agentic workspace with 7 rule files | — | Setup complete |
