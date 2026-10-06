# Milestone 7: MVP Testing, Refinement & Deployment

## Description
This milestone focuses on conducting comprehensive testing, refining the user interface, and executing the initial production deployment of the MVP.

## Key Tasks
*   Conduct comprehensive end-to-end testing of the entire system.
*   Refine the user interface based on internal feedback.
*   Execute the initial production deployment of the frontend (Next.js), backend (FastAPI), and Payload CMS applications.
*   Configure production environment variables for all services.
*   Confirm that all services are communicating successfully in the production environment.
*   Ensure the application is publicly accessible and stable.
*   Set up basic monitoring and logging for all production services.

## Status
In Progress

The application is deployed and public at chat.lite.space/chat (Docker Compose stack via `scripts/run-prod.sh -d --force --local-rag`; backend, worker, Payload CMS, both frontends, Redis, Redis Stack, Mongo, Prometheus, Grafana, Alertmanager, Cloudflare tunnels). Production environment variables are configured and all services report healthy. Monitoring, structured logging and Discord alerting are operational. The nightly golden eval (`run_golden_eval`, 75 questions, caches bypassed) is the regression gate; uncached baseline on 2026-10-06 is 62/75.

Remaining before this milestone closes:
*   Frontend end-to-end tests (Playwright) for the chat stream, source chips, refusals and the composer notice. Both frontends currently only type-check (`tsc --noEmit`).
*   Close the basic-question retrieval misses recorded in `MISSION_CONTROL.md` (what-is-litecoin, Foundation, LTC vs BTC, confirmations, Lightning) so they answer from the KB rather than the web tier.

## Dependencies
*   In Progress: Milestone 6 (MVP Content Population & Validation)

## Acceptance Criteria
*   A final round of end-to-end testing is completed and passed.
*   Any critical or major bugs discovered during testing are resolved.
*   The Next.js frontend is successfully deployed to Vercel.
*   The FastAPI backend is successfully deployed to its hosting environment.
*   All services (Frontend, Backend, CMS, DB) are correctly configured with production environment variables and are communicating successfully.
*   The Litecoin Knowledge Hub is publicly accessible and stable.
*   Basic monitoring and logging are confirmed to be operational for all production services.
