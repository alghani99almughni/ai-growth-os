# AI Visibility (AEO/GEO) Module Architecture

## Status
Planning baseline for the feature branch `feature/aeo-geo-visibility-platform`. This document is not a claim that the module is production-ready.

## Product goal
Add Answer Engine Optimization (AEO) and Generative Engine Optimization (GEO) capabilities inside the existing multi-tenant AI Growth OS. It should reuse the current tenant identity, authentication, business dashboard, integration settings, AI provider abstraction, and deployment model where appropriate. It is not a separate SaaS or a parallel account system.

## MVP capabilities
1. Tenant-scoped brand/business profile and website URL.
2. Competitor profiles, each owned by the same tenant.
3. Website technical/content audit with transparent findings and actionable recommendations.
4. Query library: questions customers may ask AI/search engines about the business, services, and location.
5. Visibility check runs with provider, method, timestamp, status, and source evidence.
6. Historical results and trend reporting.
7. Action queue that turns findings into reviewable recommendations; no automatic publishing in MVP.
8. Tenant usage counters and platform-admin visibility into failures/usage.
9. Exportable report with scope, run date, method, limitations, and evidence.

## Proposed logical flow
Tenant dashboard -> authenticated tenant API -> domain/service layer -> persisted audit/query/run records -> background execution for longer jobs -> provider adapters -> normalized result + evidence -> dashboard/history/report.

Short, deterministic operations may run inline. Network scans and provider checks should use the repository's existing background-job conventions if available. Do not introduce Redis/Celery or another queue until the current deployment and worker setup have been inspected and a concrete need established.

## Core components
- **Brand & competitor registry:** tenant-owned business metadata and competitor domains.
- **Audit engine:** fetches permitted public pages and evaluates metadata, headings, canonical URLs, robots/sitemap signals, structured data presence, content coverage, and basic accessibility/performance hints where supported.
- **Query planner:** tenant-owned prompts/questions with locale, intent, topic, and active state.
- **Visibility adapters:** provider-specific integrations behind a small interface; provider availability and authentication are configuration-driven.
- **Evidence normalizer:** stores the exact query, provider/method, time, observed mention, cited URLs, raw/normalized status, and errors.
- **Recommendation engine:** deterministic checks first; AI-assisted drafting only when configured, clearly labelled, and grounded in stored evidence.
- **Reporting:** summaries and deltas derived from persisted records, never fabricated.
- **Usage guard:** limits jobs and external calls per tenant/plan.

## Data and tenancy
Every tenant-owned record must include `tenant_id` and every read/write must be scoped using the authenticated user's authorized tenant context. Never trust a tenant ID from the request path alone. Reuse existing `require_tenant` and authorization patterns where appropriate. Cross-tenant tests are required for each new endpoint.

## Visibility measurement truthfulness
Do not promise guaranteed placement or rankings in AI answers. Label results as one of:
- **Search-grounded observation:** a provider response returned evidence/citations and those were stored.
- **Model-sampled observation:** a model was asked a question without a grounded live search source.
- **Website audit:** deterministic checks against pages fetched during a specific run.

Do not combine these into a single score without explaining the method and coverage. Persist failures and partial results; absence of a mention in a sample is not proof of universal invisibility.

## API shape (proposal; adapt to existing conventions)
- `GET/POST /api/v1/tenants/{tenant_id}/visibility/brand`
- `GET/POST /api/v1/tenants/{tenant_id}/visibility/competitors`
- `GET/POST /api/v1/tenants/{tenant_id}/visibility/queries`
- `POST /api/v1/tenants/{tenant_id}/visibility/audits`
- `GET /api/v1/tenants/{tenant_id}/visibility/audits/{audit_id}`
- `POST /api/v1/tenants/{tenant_id}/visibility/checks`
- `GET /api/v1/tenants/{tenant_id}/visibility/checks`
- `GET /api/v1/tenants/{tenant_id}/visibility/reports/summary`

These routes are a design proposal, not a guarantee they have already been implemented. Before adding them, check existing routes to avoid collisions and follow existing API naming/response conventions.

## Rollout boundaries
- Keep all work on this feature branch.
- Do not change Render configuration, production environment variables, or production database schema as part of documentation work.
- Do not deploy automatically.
- Merge/deploy only after tests, security review, and explicit go-live approval.
