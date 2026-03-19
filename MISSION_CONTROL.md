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
| 8 | Implement Trust and Feedback Features | Planned | Source citations, user feedback loops |
| 9 | Implement Contextual Discovery | Completed | Follow-up questions, search grounding |
| 10 | Upgrade Retrieval Engine | Cancelled | Scope absorbed into M3 improvements |
| 11 | Transaction & Block Explorer | Completed | Litecoin Space API: tx, address, block, fees, mempool, tip |
| 12 | Market Data & Insights | Completed | Price (5 currencies), hashrate, difficulty, adjustment progress |
| 13 | Developer Documentation & Resources | Planned | API docs, integration guides |

**Summary:** 8 completed, 2 in progress, 1 cancelled, 2 planned

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

- **Location:** `backend/tests/` (31 test files)
- **Last known state:** 121+ passing, 36 skipped, 30 non-blocking warnings
- **Run:** `pytest backend/tests/ -v`

### Coverage by Domain

| Domain | Test Files | Coverage |
|--------|-----------|----------|
| Security | 7 files | Strong — abuse prevention, rate limiting, webhook auth, headers |
| RAG Correctness | 6 files | Moderate — intent, FAQ, memory, graph state machine, streaming |
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
| `backend/rag_pipeline.py` | ~1670 | RAG orchestration — the brain |
| `backend/rag_graph/state.py` | ~65 | Graph state definition (TypedDict) |
| `backend/rag_graph/graph.py` | ~80 | Graph wiring and conditional edges |
| `backend/rag_graph/nodes/blockchain_lookup.py` | ~250 | Live blockchain data node (Litecoin Space API) |
| `backend/services/blockchain_client.py` | ~330 | Async API client, Pydantic models, Redis caching |
| `backend/services/intent_classifier.py` | ~350 | Intent detection (greetings, FAQ, blockchain lookups) |
| `backend/data_models.py` | 250 | API Pydantic v2 models |
| `backend/main.py` | — | FastAPI app, public routes |
| `payload_cms/src/payload.config.ts` | — | CMS configuration |

## Recent Activity

| Date | Change | Milestone | Status |
|------|--------|-----------|--------|
| 2026-03-19 | Fixed blockchain API: plain-text endpoints, price endpoint path, 404 error handling, price freshness timestamps | M11/M12 | Completed |
| 2026-03-19 | Fixed intent detection: blockchain queries now fire regardless of is_dependent flag; removed static data disclaimer from system prompt | M11 | Completed |
| 2026-03-19 | Litecoin Space blockchain data integration: API client, graph node, intent detection, 7 frontend components, SSE protocol extension | M11/M12 | Completed |
| 2026-03-19 | Initialized `.cursor/rules/` agentic workspace with 7 rule files | — | Setup complete |
