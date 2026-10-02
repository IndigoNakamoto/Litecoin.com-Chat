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
| 8 | Implement Trust and Feedback Features | Completed | Structured source chips (title/URL/updated_at/stale), unverified web chips, abstention, thumbs feedback filed against source docs, admin `/feedback` |
| 9 | Implement Contextual Discovery | Completed | Follow-up questions, search grounding |
| 10 | Upgrade Retrieval Engine | Cancelled | Scope absorbed into M3 improvements |
| 11 | Transaction & Block Explorer | Completed | Litecoin Space API: tx, address, block, fees, mempool, tip, mining pools |
| 12 | Market Data & Insights | Completed | Price (5 currencies), hashrate, difficulty, adjustment progress |
| 13 | Developer Documentation & Resources | In Progress | Source registry (`doc_sources.yaml`: Core docs/release notes, MWEB LIPs, Space API, litecoin.com) on weekly ARQ cron → Payload drafts; editors publish |

**Summary:** 9 completed, 3 in progress, 1 cancelled, 0 planned

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
    │  LangGraph RAG State Machine (11 nodes, 4 conditional exits) │
    │  sanitize → safety_gate (pin / refuse / escalate / audience) │
    │     → route → prechecks → blockchain_lookup (live API)       │
    │              → semantic_cache → decompose → retrieve         │
    │              → resolve_parents → spend_limit → generate      │
    │  Hierarchy: KB → live data → web (unverified) → abstain      │
    │                            |                                  │
    │  RAG Pipeline (streaming + search grounding fallback)        │
    │                                                               │
    └──────────┬──────────────┬──────────────────┬─────────────────┘
               |              |                  |
           MongoDB         Redis            Payload CMS
         (persistence)   (cache/rate)     (content authoring)
                                          webhooks → vector sync
```

## Verification Gates

### Test Suite

- **Location:** `backend/tests/` (41 test files; eval harness is opt-in via `pytest -m eval`, and runs nightly as the ARQ `run_golden_eval` job)
- **Last known state (2026-10-01, host, HF offline):** 328 passed, 15 skipped, 1 failed (`test_admin_redis_stats` needs Docker `redis` host). `test_conversational_memory.py`, `test_rag_pipeline.py`, `test_local_rag_*.py` need live Mongo/Ollama/Infinity and were excluded on the host; run them in the backend container.
- **Run:** `pytest backend/tests/ -v -m "not eval"` (CI). Golden set live: `EVAL_RETRIEVAL=1 pytest -m eval backend/tests/eval`. Nightly baseline (2026-10-02): 56/62.
- **Redeploy:** always `./scripts/run-prod.sh -d --force --local-rag` (recreates `redis_stack` with its password; a bare `compose up` misses the URL-encoded Mongo creds). After Article schema changes: admin Jobs → `reingest_all_published` → `Reindex vectors` → `Reload index into API`.

### Coverage by Domain

| Domain | Test Files | Coverage |
|--------|-----------|----------|
| Security | 7 files | Strong — abuse prevention, rate limiting, webhook auth, headers |
| RAG Correctness | 7 files | Moderate — intent, FAQ, memory, graph state machine, streaming, context `format_docs` |
| Blockchain Data | 3 files | Good — API client, intent detection, graph node routing |
| Admin API | 3 files | Good — auth, settings, spend limits |
| Operations | 2 files | Partial — HTTPS redirect, spend limit integration |

### Known Gaps

- No dedicated chat API endpoint test (`test_api_chat.py`); `test_chat_stream_follow_ups.py` covers the SSE contract (chips, `requestId`, `webSources`, `abstained`)
- No Payload sync lifecycle test (`test_sync_payload.py`); `test_cache_invalidation.py` covers the invalidation helper
- No frontend tests (Playwright / component); both frontends type-check (`tsc --noEmit`)
- `payload_cms/src/lib/syncWebhook.ts` (retry/backoff) is not unit-tested; verify by publishing an article with the backend stopped and watching the CMS log retry
- Abstain criterion is the cross-encoder top score (`RAG_ABSTAIN_CE_SCORE=-3.0`), calibrated once on prod (on-topic >= -1.4, off-topic <= -4.5). Re-check after any embedding/reranker model change; the nightly golden eval's `abstain-*` ids will catch drift.
- 21+ tests skip when local services (Ollama, Infinity, Redis Stack) unavailable
- 9 tests skip without `fakeredis`

### Definition of Done

Per `docs/testing/TEST_SUITE_IMPLEMENTATION_PLAN.md`: target 80-90% coverage, 85%+ for critical modules. All RAG, auth, rate limiting, spend limit, and webhook auth tests must pass before deployment.

## Key Files

| File | Lines | Role |
|------|-------|------|
| `backend/rag_pipeline.py` | ~1600 | RAG orchestration — the brain (streaming + graph invoke) |
| `backend/rag/generate.py` | ~170 | Non-stream generation (chain, grounding, cache write-back) |
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
| 2026-10-02 | **Sources, latency, ops review (deployed).** *Sources:* chips no longer show the date (tooltip only) and are clickable: link precedence `pinned_url` → article `sourceUrl` (litecoin.com page, or YouTube → inline `youtube-nocookie` player, CSP `frame-src` added) → new public reader `chat.lite.space/chat/articles/{id}` (`frontend/src/app/articles/[id]`, server-fetches published articles from Payload via `PAYLOAD_INTERNAL_URL`; 404 for drafts). `ARTICLE_PUBLIC_BASE_URL=https://chat.lite.space/chat` set in prod env; CMS host is no longer a fallback (it 404s). Chips capped at 5 (`SOURCE_CHIPS_MAX`). Synthetic FAQ docs now inherit provenance metadata. *Latency:* removed the 25 ms/word frontend typing delay (rAF-coalesced render) — this alone was ~6 s on a long answer; cached answers replay in 64-char chunks instead of 1 SSE event/char. **Semantic cache had never worked in prod**: redis-py 5.x module is `indexDefinition` (import fallback added) and `redis_stack` lacked `--requirepass` (recreated via `run-prod.sh --local-rag`); now `earlyType=redis_vector` hits in ~1.3 s. Per-stage timings (`t_embed/vector_bm25/sparse/cross_encoder/parents/decompose_ms`) in metadata, `chat_ttft_ms` log, `rag_stage_duration_seconds{stage}` + Grafana p50/p95 panels. Measured: embed 60-600 ms (Infinity), vector+BM25 ~3 ms, cross-encoder 300-460 ms (was the cost; now off the event loop via `to_thread`, input capped at 10, `max_length=256`), decompose LLM gate tightened to real compounds. Live first-token now 1.1-1.9 s (was 2-4 s). *Ops follow-through:* topicality gate — off-topic low-confidence questions abstain immediately (0.8 s, no LLM); only Litecoin-related gaps take the web tier (`is_litecoin_related`). `rag/generate.py` now applies the same hierarchy (the graph `generate` node had been answering low-confidence questions in `aquery`). Intent: definitional/mechanism fee & mempool questions route to RAG; live-value phrasing routes to lookup; lookup errors keep `intent=blockchain_lookup`. **Bug:** `get_hashrate` used `/v1/mining/hashrate/1w`, which hangs >25 s on litecoinspace.org; switched to `/3d` (0.2 s). Cluster job gate: freq ≥3, topic set, ≥4 words, safety-router pass, on-topic (first night drafted "Live Agent" and a debit-card question — delete those two drafts in the CMS). **Worker fixes:** image has no `scripts/`, so `reindex_vectors`/`cleanup_orphans` ARQ jobs had never run, and the worker did not share `faiss_index_data` — both mounted now; new on-demand `reingest_all_published` job (re-chunks all articles so new Article fields reach chunk metadata) and admin `POST /jobs/reload-index` (+ Jobs page button) to load a rebuilt index into the running API. Ran: reingest 37/37 → reindex (356 chunks) → reload. Golden eval re-run: **56/62 (90%)**, 7 fixed, 0 regressions; remaining = 4 content gaps (confirmations, SegWit, UTXO, mempool — Monday queue) + 2 Litecoin-related gaps now expected to take the web tier (`gap-*` ids). Tests: 364 passed host (+ `test_blockchain_intent` explain-vs-lookup, cluster gate, topicality, decompose gate, CE abstain). | M3 / M7 / M8 / M9 | Completed |
| 2026-10-01 | **Deployed to prod** via `run-prod.sh -d --force` (all images rebuilt; backend, worker, payload_cms, frontend, admin_frontend, new `alertmanager` recreated; Prometheus reloaded — Alertmanager target active, 7 rule groups incl. `trust_surface_alerts`). Worker registered 16 functions incl. 5 cron jobs. Live smoke: MWEB answers with 5 chips; "Should I buy" refuses in 0.1s; scam report escalates; fees card carries `_provenance`. **Two fixes found by the smoke test:** (1) `utils/challenge.py` indexed `result[1]` but Lua `{1, nil}` returns a 1-element list, so every expired/invalid challenge 500'd instead of returning the 403 the frontend retries on — fixed. (2) The FAISS-L2 abstain floor did not separate on/off-topic on this corpus (sourdough 0.39 vs MWEB 0.78): off-topic questions were answered from the web with unrelated Litecoin articles shown as sources. Switched the criterion to the cross-encoder top `rerank_score` (`RAG_ABSTAIN_CE_SCORE=-3.0`; measured on-topic >= -1.4, off-topic <= -4.5; L2 floor now off by default). After redeploy: sourdough → `abstained=true`, no sources, declines; Solidity → low-confidence, web tier answers about LitVM, labelled unverified, no KB chips. Note: `rebuild-backend.sh` ends in `logs -f`, and a bare `compose up` misses the URL-encoded Mongo creds `run-prod.sh` computes (backend came up Mongo-less once) — use `run-prod.sh -d --force` for redeploys. Tests: `test_rag_graph_state_machine.py` +3 (CE abstain, no-score, disabled). | M7 / M8 | Completed |
| 2026-10-01 | **Foundation Bot Gap Roadmap (Phases 0-3 + ops).** *Phase 0 (rot):* Redis vector cache gets a 7d TTL (`REDIS_CACHE_TTL_SECONDS`), stores `is_grounded` + cited `payload_ids`; CMS webhook invalidates every cache layer for the changed article (`sync/payload.invalidate_cached_answers_for`); cache hits replay `isGrounded`; Gemini calls go through `services/llm_resilience.py` (breaker + bounded retry, "answer service unavailable" instead of a guess); `payload_breaker` wired into draft generator; `kb_sources` passed to gap detector; dead `SEARCH_GROUNDING_*` + `PROVENANCE_MARKER` removed; Litecoin Space outage says "tool down". *Phase 1 (trust):* SSE `sources` event carries structured chips (`serialize_sources_for_client`: title, URL, `updated_at`, stale flag) and `complete` carries `webSources` (unverified), `abstained`, `requestId`; `SourceChips.tsx`, `AnswerFeedback.tsx`; abstain path (`low_similarity` from `RAG_ABSTAIN_L2_DISTANCE`, `KB_ABSTAIN_RESPONSE`, `rag_abstain_total`, queued as gap, never cached); hierarchy KB → live → flagged web → abstain (`RAG_ABSTAIN_BEFORE_SEARCH`); `_provenance` (fetched_at + endpoint) on every live card incl. new mining-pool cards; thumbs feedback `POST /api/v1/chat/feedback` → Mongo `answer_feedback` keyed to `source_payload_ids`, admin `/feedback` by-source view; `LLMRequestLog` gains `source_payload_ids`/`is_grounded`/`abstained`. *Phase 2 (intents):* new `safety_gate` node + `services/safety_router.py` (REFUSE: advice/seed/legal-tax/impersonation/injection/harm; ESCALATE: scam/bug/partnership/press with env-overridable links; audience label → prompt profile via `audience_note`); prompt-injection hits now refuse instead of being discarded; incident pin (`services/incident_pin.py`, Redis `admin:incident_pin`, admin `GET/PUT/DELETE /incident-pin`, dashboard card) short-circuits before cache; golden set grown 14 → 66 with `expected_behavior`, `backend/eval/golden_runner.py` scores behavior + citation and diffs vs last run. *Phase 3 (freshness):* Article `sourceTier`/`lastReviewedAt`/`reviewIntervalDays` → chunk metadata → chips; `payload_cms/src/lib/syncWebhook.ts` retry/backoff; ARQ cron (`jobs/maintenance.py`): nightly stale report, nightly golden eval, daily gap clustering → one CMS draft per cluster, weekly embedding reconcile (re-embeds lost webhooks), weekly `ingest_doc_sources` from `data_ingestion/doc_sources.yaml`; `scripts/ingest_doc_sources.py`. *Ops:* Alertmanager service → Discord (`monitoring/alertmanager.yml`), new metrics `rag_abstain_total`/`rag_refuse_total`/`tool_error_total`/`incident_pin_served_total`/`answer_feedback_total`, trust-surface alert rules + Grafana row, `send_ops_alert`, admin `/jobs` page (`GET /jobs/status`, `POST /jobs/maintenance/{name}`). Tests: +5 files (`test_cache_invalidation`, `test_llm_resilience`, `test_trust_surface`, `test_maintenance_jobs`, expanded `test_eval_scaffold`); host run 328 passed / 15 skipped / 1 env failure. Both frontends `tsc` clean. **Deploy notes:** rebuild backend, worker, payload_cms, frontend, admin_frontend; `docker compose config` validated; regenerate Payload types; existing published articles need a reindex to pick up `sourceTier`/review fields; set `DISCORD_ALERTMANAGER_WEBHOOK_URL` (or it falls back to `DISCORD_WEBHOOK_URL`). | M3 / M7 / M8 / M9 / M13 | M8 Completed; others In Progress |
| 2026-08-29 | **CMS admin “Fetching user failed”:** local prod compose had `PAYLOAD_PUBLIC_SERVER_URL=https://cms.lite.space`, so `http://localhost:3001/admin` CORS-blocked `/api/users/me`. Override now forces `http://localhost:3001`; localhost is always in CORS/CSRF; session cookies are Secure only on https. CMS image rebuilt. Browser: login loads, no fetch error. | M5 | Completed |
| 2026-08-29 | **Knowledge-candidate publish 403:** Payload create failed because `PAYLOAD_API_KEY` is a shared env secret, not an enabled user API key (`req.user` was null). CMS now treats a matching `users API-Key` / `X-Payload-Service-Key` as a trusted service credential for article create + status. Probe POST returned 201; payload_cms image rebuilt and recreated. Tests: `test_article_draft_generator.py` 3 passed. Full host `pytest backend/tests/` still hits `/app` FAISS path errors outside Docker. | M6 / M9 | In Progress |
| 2026-08-23 | **Post-pull prod recreate:** rebuilt baked images from current `main` (`run-prod.sh -d --force`) so frontend/admin/backend/worker left 7-week-old images. Started missing ARQ `worker`. Wired worker Mongo/Redis URLs in `docker-compose.override.yml`; ARQ DSN no longer sends empty Redis username (`backend/jobs/redis_settings.py`). Disabled worker image `/health/live` check. Started host Infinity (`./scripts/run-local-rag.sh`; bge-m3 on :7997) so retrieval is not circuit-open. Tests: `test_jobs_enqueue.py` 4 passed in backend image (host skips 2 without `arq`). | M7 | In Progress |
| 2026-08-21 | **Ask-next / chip click-through:** composer is no longer `sticky` over the thread. Chat column is flex (`messages flex-1` + input `shrink-0`) so Follow-up "Ask next" chips and empty-state suggested questions sit above the input and stay clickable. Files: `frontend/src/app/page.tsx`, `ChatWindow.tsx`, `InputBox.tsx`, `FollowUpQuestions.tsx`. Frontend-only; pytest not run. | M9 | In Progress |
| 2026-08-21 | **Search grounding on locally:** compose `USE_SEARCH_GROUNDING=true` (recreate backend/worker). In-corpus `What is MWEB?` stayed ungrounded, first token 1.89s. Gap query (Kaspa / blockDAG / Pectra) logged `Context coverage gap → prompting search for: kaspa, blockdag, pectra`, SSE `isGrounded=true` via coverage-fallback (SDK `grounding_metadata` still absent on the last stream chunk), first token 4.47s. Repeat of the same query hit cache and replayed `isGrounded=false`. | M9 | In Progress |
| 2026-08-21 | **Suggested chips:** compose backend/worker `PAYLOAD_URL=http://payload_cms:3000` (env_file localhost:3001 is host-only). Seed public questions into local Payload: `./scripts/seed-suggested-questions-from-prod.sh`. Recreate: `docker compose -f docker-compose.dev.yml up -d --force-recreate backend worker`. Browser chips still hit `localhost:3001`. | M9 | In Progress |
| 2026-08-21 | **TTFT slice:** vocab-first short-query + rewrite skip (`is_dependent` === frozen tokens/prefixes in `backend/rag/history_dependency.py`). Local compose `USE_SEARCH_GROUNDING=false` (ungrounded TTFT numbers). MiniLM lifespan warm + HF cache volume. CE skip on FAISS L2 `<= CROSS_ENCODER_SKIP_DISTANCE` (single-query). Logs `chat_ttft_ms` (`t_sse`, `t_route_end`, `t_retrieve_end`, `t_first_token`). **Ship bar is p95 first-token &lt; 3s on a warm process when skips fire — not complete RAG answers in 3s.** Known miss: standalone-looking follow-ups like “the second one” drop history. Recreate: `docker compose -f docker-compose.dev.yml up -d --force-recreate backend worker`. | M3 | In Progress |
| 2026-08-21 | **Strangle C first slice:** parallel multi-query retrieve (`asyncio.gather`); persist Infinity `sparse_embedding` at ingest and reuse at retrieve; thin `generate` graph node (`backend/rag/generate.py`, streaming stays in `astream_query`); eval scaffold (`pytest -m eval`, `backend/tests/eval/golden_questions.yaml`). CI default is `-m "not eval"`. | M3 / M7 | In Progress |
| 2026-08-21 | **Strangle A+B (build machine):** dependency-class health (`/health/ready` 503 on Redis/Mongo fail; `/health/detailed` auth; compose `/health/live`); `justfile` + `scripts/preflight.sh`; cache-by-default rebuilds; diagnose matrix; GitHub Actions CI; ARQ worker + admin job enqueue; CMS pull script `scripts/pull-cms-from-prod.sh`. Tests: `pytest backend/tests/test_health.py backend/tests/test_jobs_enqueue.py` — 10 passed. Full suite not run here (no Docker / HuggingFace in this environment). Set `GOOGLE_API_KEY` in `backend/.env` then `just up dev` and `./scripts/pull-cms-from-prod.sh`. | M7 | In Progress |
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
