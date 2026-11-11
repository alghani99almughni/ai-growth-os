# AEO/GEO Visibility Module — Implementation Roadmap

## Working branch
`feature/aeo-geo-visibility-platform`

## Phase 0 — Repository reconnaissance
- [x] Confirm repository and default branch.
- [x] Create isolated feature branch from `main`.
- [ ] Map existing frontend routes/navigation and tenant dashboard layout.
- [ ] Inspect FastAPI auth, tenant guards, SQLAlchemy models, migrations, provider adapters, job patterns, tests, and Render configuration.
- [ ] Identify exact existing patterns to reuse before adding runtime code.

## Phase 1 — Foundation
- [x] Architecture overview.
- [x] Proposed database design.
- [x] Security/reliability gates.
- [x] Phased roadmap.
- [ ] Agree endpoint/model naming with existing conventions.
- [ ] Add schema/models and migrations only after confirming migration workflow.
- [ ] Add tenant-scoped service and API tests.

## Phase 2 — Website audit MVP
- [x] Public HTTP/HTTPS URL validation and connection-pinned fetcher; all DNS answers must be globally routable.
- [x] Synchronous single-homepage audit endpoint and tenant-scoped audit/finding persistence (not yet a background job).
- [x] Initial deterministic checks: title, meta description, H1 structure, canonical, robots noindex, and JSON-LD presence.
- [x] Tenant dashboard action for starting an audit and viewing findings.
- [ ] Per-tenant/global rate limits, asynchronous job states, sitemap/internal-link crawl, and deeper page-budget controls.
- [x] Fetch timeouts, no redirect following, and a 500 KB response cap.

## Phase 3 — AI visibility MVP
- [x] Tenant brand profile, competitor profiles, and customer-question library.
- [x] Official provider API adapters for Gemini, Perplexity, Grok, and Claude.
- [x] Store provider/model, measurement method, timestamps, answer excerpt, and citation evidence.
- [x] Historical observations and tenant-scoped visibility history.
- [x] Clearly label model-only samples versus search-grounded observations based on returned evidence.
- [ ] Transparent coverage metrics, scheduled checks, usage metering, and evidence-backed reporting.

## Phase 4 — Reporting and usage controls
- [ ] Tenant report with evidence-backed recommendations.
- [ ] Usage counters and plan limits aligned to existing subscription/billing behavior.
- [ ] Failure/partial states and retry controls.
- [ ] Export format and retention policy.

## Phase 5 — Verification and release
- [ ] Unit, integration, tenant-isolation, SSRF, retry, and idempotency tests.
- [ ] Frontend/backend build and regression checks.
- [ ] Disposable database migration/rollback test.
- [ ] Preview environment validation.
- [ ] Pull request review and explicit go-live approval.

## Scope guardrails
- This is a module inside AI Growth OS, not a separate SaaS.
- Do not duplicate tenant/auth/billing/integration systems.
- Do not change the production branch or production deployment during development.
- Do not claim implementation is complete until checks are executed and results recorded.
- Never promise placement in AI answers; provide measured observations with method and evidence.
