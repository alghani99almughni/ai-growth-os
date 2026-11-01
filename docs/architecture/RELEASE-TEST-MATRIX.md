# AEO/GEO Visibility — Release Test Matrix

This checklist is the release gate for the visibility feature. A green CI run is necessary but not sufficient. Do not merge to the default branch or deploy to production based only on this document.

## 1. Functional and regression tests

- [ ] Brand profile create/read/update; invalid domain and boundary inputs rejected.
- [ ] Competitor create/list/delete and tenant isolation.
- [ ] Query create/list, intent validation, empty and maximum-length values.
- [ ] Website audit: successful HTML, missing title/description/H1/canonical/JSON-LD, noindex, redirect, HTTP error, non-HTML, timeout, connection error, oversized response.
- [ ] Audit history and detail are tenant-scoped; unknown/cross-tenant IDs do not disclose data.
- [ ] Existing voice intent, booking extraction, language detection and routing regression tests remain green.
- [ ] Frontend production build and TypeScript checks succeed.

## 2. Security and privacy

- [ ] Validate authentication and authorization for every new endpoint.
- [ ] Prove Tenant A cannot read, mutate, or infer Tenant B data for brand, competitors, queries, audits, findings and observations.
- [ ] Validate malformed domains, credentials, unsupported ports, localhost, IPv4/IPv6 literals, private/link-local/reserved DNS answers, metadata-service addresses and redirects to private destinations.
- [ ] Test DNS rebinding resistance; pre-request DNS validation alone is not sufficient if the HTTP client performs a second resolution.
- [ ] Verify response size, content-type, connection/read timeout and per-tenant/global rate limits.
- [ ] Ensure provider secrets and raw sensitive response bodies are never exposed in UI, API errors, reports or logs.
- [ ] Confirm provider integrations are disabled gracefully when credentials are absent.

## 3. Performance and reliability

Run tests against a disposable/staging environment, not production data.

- [ ] Record baseline p50/p95/p99 latency for list/read endpoints with representative data volumes.
- [ ] Exercise 1, 5, 10 and 25 concurrent read requests; record latency, errors and resource use.
- [ ] Exercise bounded audit calls with slow, disconnected, large and non-HTML responses.
- [ ] Verify timeouts terminate work and do not leave open connections or database transactions.
- [ ] Verify provider failure/rate limiting produces explicit partial/failed status, bounded retry behavior and no duplicate usage accounting.
- [ ] Verify pagination/limits prevent unbounded reads; inspect query plans and indexes with representative data.
- [ ] Record CPU, memory, database connection use and external request counts during load tests.
- [ ] Do not declare a performance target met until actual measurements and environment details are attached.

Initial proposed staging targets (confirm or adjust using the actual hosting tier and product SLO):
- Read endpoints: p95 under 500 ms at 25 concurrent requests.
- Non-network unit tests: complete in under 30 seconds for the visibility subset.
- Audit network calls: bounded by configured connection/read timeouts and response-size cap.
- Error rate: zero unexpected 5xx responses in the defined steady-state load run.

## 4. Engineering and release checks

- [ ] API tests and all existing regression tests pass in CI.
- [ ] Frontend production build, lint/type checks and route smoke tests pass.
- [ ] Database migration upgrade and rollback tested against a disposable database.
- [ ] Dependency/security scan reviewed; critical/high findings fixed or explicitly risk-accepted.
- [ ] Observability records request failures, duration, status and safe error codes without secrets.
- [ ] Manual smoke test verifies a normal tenant and a denied cross-tenant request.
- [ ] Rollback procedure and required environment variables documented.
- [ ] Pull request review and explicit release approval completed.

## 5. Evidence report

For each run, record:
- commit SHA and branch;
- workflow/run link and environment;
- exact commands and test counts;
- pass/fail/skip counts;
- performance workload, data volume and p50/p95/p99;
- defects found, severity, fix commit and retest evidence;
- open risks, assumptions and blocked checks.

Use only these states: PASS (measured evidence), FAIL (reproducible defect), WARNING (risk/known limitation), NOT TESTED (missing evidence or prerequisite).

## Current known limitation

The initial audit is a single-page public homepage metadata check. It is not a live AI-answer/provider visibility measurement and does not establish rankings. SSRF-safe connection pinning, tenant-isolation coverage, rate limiting, provider integration, full frontend build, migration rollback and measured load tests must be verified before production release.
