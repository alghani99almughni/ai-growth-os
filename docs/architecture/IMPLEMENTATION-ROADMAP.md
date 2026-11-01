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
- [ ] SSRF-safe URL validation and guarded fetcher.
- [ ] Audit job and findings model.
- [ ] Initial deterministic checks: title, meta description, heading structure, canonical, robots/sitemap signals, structured-data presence, broken/internal links within a strict page budget.
- [ ] Tenant dashboard for starting an audit and viewing findings.
- [ ] Rate limits, caps, timeout handling, and audit history.

## Phase 3 — AI visibility MVP
- [ ] Tenant brand profile, competitor profiles, and query library.
- [ ] Provider adapter selected from the existing integrations/provider pool after capability verification.
- [ ] Store exact method/provider/time and citation evidence.
- [ ] Historical observations and transparent coverage metrics.
- [ ] Clearly label model-only samples versus search-grounded observations.

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
