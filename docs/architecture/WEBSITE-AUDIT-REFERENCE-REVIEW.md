# Website Audit Reference Review — AI Growth OS

**Review date:** 2026-10-26  
**Target:** `feature/aeo-geo-visibility-platform` at `38bd91d9ba262cdcd086fd736b54c54a9616ae12`  
**Purpose:** Assess the 16 user-supplied GitHub references for relevance to the Website Audit module. This document records research and implementation decisions; it does not authorize merge or deployment.

## Executive decision

The references are a mixed set, not 16 interchangeable website-audit engines. Reuse patterns, not whole projects. The strongest direct reference is `DrVerzide/headers-inspector` for passive HTTP security-header checks. `SuperLogicAI/production-readiness` is a useful evidence-first production checklist, and selected PRs/issues offer QA, safe reporting, threat-model, and CI-gate practices. Several links are unrelated to website auditing or concern host privacy/network infrastructure.

**Security gate:** Website audit must remain unavailable until server-side access is gated and SSRF/DNS-rebinding protections are enforced at connection time. The current branch's UI has been paused, but source review found `POST /api/v1/tenants/{tenant_id}/visibility/audits` still exists in `apps/api/app/routes_visibility.py`. Its `_validated_public_url` checks DNS results, then a normal `httpx.Client` fetches the hostname separately. That second resolution can differ; disabling redirects and checking the initial DNS result do not alone prevent DNS rebinding. This is a real backend gate, not merely a UI issue.

## Reference-by-reference disposition

| # | Reference | Relevance to website audit | Decision |
|---:|---|---|---|
| 1 | [SuperLogicAI/production-readiness](https://github.com/SuperLogicAI/production-readiness) | High for evidence-first audit workflow: trust boundaries, auth/tenant isolation, migrations, rate limits, tests, observability, recovery, cost controls. It is an agent skill/blueprint, not a crawler. Repository metadata reports MIT. | Adopt its checklist/evidence discipline as an internal readiness checklist; do not copy the entire skill as an execution engine. |
| 2 | [DrVerzide/headers-inspector](https://github.com/DrVerzide/headers-inspector) | High for passive HTTP response-header checks and explainable A–F scoring. README lists CSP, HSTS, clickjacking controls, nosniff, Referrer-Policy, Permissions-Policy, and version disclosure. Repository metadata reports MIT. | Reuse the check taxonomy and test/report pattern after reviewing implementation details; integrate as a native check rather than requiring a separate CLI process. |
| 3 | [jdgiles26/macsec-agents](https://github.com/jdgiles26/macsec-agents) | Low: audits Apple/macOS host inventory and CVEs, not public website content. Repository metadata reports MIT. | Do not integrate its host scanner. The general ideas of severity scoring, history/diffs, graceful degradation, and JSON/Markdown/HTML/SARIF reports may inform report design only. |
| 4 | [Mrsoulgod/TheUrbanWon](https://github.com/Mrsoulgod/TheUrbanWon) | Unverified/low: repository description presents a volunteer white-hat website-hardening service, but a README could not be retrieved at the expected path and no license was exposed in repository metadata. | No code reuse. Treat as a service/approach reference only until inspectable source and a reuse license are confirmed. |
| 5 | [zeroFhacker/zerotrace](https://github.com/zeroFhacker/zerotrace) | Low for auditing a customer's website: it primarily measures the visitor's browser fingerprint/privacy surface. README describes a browser privacy auditor and hardening guide; repository metadata indicates MIT. | Do not add browser fingerprinting to the website audit. It is a different product and raises privacy concerns. |
| 6 | [cement-order-app PR #12](https://github.com/amankeshri7542/cement-order-app/pull/12) | Medium as a security engineering example: audit findings mapped to regression tests, auth/rate limits, bounded streams, idempotency and safe error handling. It is an open PR in another application, not an audit library. | Borrow the “finding → minimal fix → regression test” workflow; do not copy domain-specific code. |
| 7 | [THECOCONUTCOMPANY PR #55](https://github.com/fshan210/THECOCONUTCOMPANY/pull/55) | Medium for QA process: desktop/mobile browser matrix, deterministic session regression tests, route/sitemap SEO checks, build/type/lint/security gates and production-vs-preview smoke tests. Open PR; body says application code was not changed. | Use its QA matrix as inspiration for audit dashboard acceptance testing; not an audit engine. |
| 8 | [ignisign-js PR #1](https://github.com/ignisign/ignisign-js/pull/1) | Medium for security test cases: validates message origin and constrains popup URLs to avoid cross-origin message injection/open redirects. Open PR, so claims need independent verification. | Add origin/redirect concepts to our security test checklist where relevant; do not copy SDK-specific code. |
| 9 | [Finco-Protocol/Forge PR #7](https://github.com/Finco-Protocol/Forge/pull/7) | Low-to-medium for release governance: health/live/readiness separation, durable event processing, alerts backed by real integration tests and explicit production gates. This is blockchain/operations work and its PR body marks workstreams in progress. | Use only the principle of evidence-backed release gates; no website audit code reuse. |
| 10 | [LVTIT/PBL4-517 PR #57](https://github.com/LVTIT/PBL4-517/pull/57) | Low-to-medium for operational reliability: validates remote targets, sender authorization, queue recovery and truthful safety reporting. Open PR and stacked on other PRs. | General testing inspiration only; not a website-audit dependency. |
| 11 | [LowcountryDigitalWorks issue #81](https://github.com/LowcountryDigitalWorks/lowcountrydigitalworks.com/issues/81) | Medium for a controlled website-hardening workflow: evidence-first audit findings, restrictive CSP preservation, real 404 semantics, bounded repo-only changes and independent verification. It is an issue, not reusable source code. | Use evidence-first findings and regression-proofed remediation as a workflow pattern. |
| 12 | [Chain-Love PR #4254](https://github.com/Chain-Love/chain-love/pull/4254) | Very low: adds security-service provider listings to a Web3 directory; it does not implement website scanning. | No audit implementation reuse. |
| 13 | [Oakwood Golf Club issue #192](https://github.com/neckarshore-websites/oakwoodgolfclub-website/issues/192) | Low-to-medium for CI governance: a failing security-audit check blocks dependency PRs, but the issue concerns a specific dependency advisory and is not a scanning engine. | Borrow the concept of explicit security CI gates only. |
| 14 | [Message Crate issue #2894](https://github.com/messagecrate/message-crate/issues/2894) | Medium for threat modeling: distinguishes app responsibilities from reverse-proxy protections and calls out TLS, rate limits, request-size limits, sessions, headers, and audit-trail capacity. It is a design issue, not implementation code. | Use its trust-boundary checklist when designing public audit execution, quotas and proxy assumptions. |
| 15 | [ARSAS issue #380](https://github.com/masarray/arsas/issues/380) | Low: focuses on repository provenance, third-party attribution, reproducibility and maintainability. | Keep provenance/licence tracking for any code we actually reuse; no audit engine reuse. |
| 16 | [routerd issue #446](https://github.com/imksoo/routerd/issues/446) | Very low: cloud network address ownership, routing and split-brain fencing; unrelated to website auditing. | No implementation reuse. |

## Existing AI Growth OS audit gap found

Source reviewed: `apps/api/app/routes_visibility.py` and `apps/api/tests/test_visibility_audit.py`.

The current audit is a bounded first-page HTML/SEO parser, not yet a comprehensive audit product. The parser currently recognizes title, meta description, canonical URL, robots meta, H1 count, and presence of JSON-LD. The request path applies a timeout, disables automatic redirects, and caps the response body at 500,000 bytes. Tests cover URL string validation, basic metadata parsing, noindex detection and body-size limits.

Important gaps before re-enabling:

1. **P0 security gate — backend feature flag / server-side disable:** the audit endpoint exists even though the frontend action is disabled. The API must reject audit execution by default until the secure fetcher passes its acceptance tests.
2. **P0 SSRF/DNS rebinding:** validate all A/AAAA results, reject every non-global/reserved destination, and pin the actual connection to the validated address while preserving hostname, TLS SNI and certificate validation. Revalidate each redirect hop if redirects are ever enabled. Cover IPv4-mapped IPv6 and unusual IP forms. Add network egress restrictions as defense in depth.
3. **Authorization and quotas:** retain tenant authorization; add explicit per-tenant/user rate limits, concurrent scan limits and hard page/time/byte budgets before multi-page crawling.
4. **Safer fetching:** restrict schemes and ports; no user-controlled headers, credentials, cookies or proxy overrides; don't return raw upstream bodies or internal error details.
5. **Security-header audit:** add passive checks for CSP, HSTS, frame-ancestors/X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy, server/version disclosure, cookie flags where applicable, and TLS/certificate status.
6. **SEO and discovery:** add robots.txt, sitemap parsing, redirect/canonical consistency, HTTP status, title/description lengths, headings, image alt text, language/hreflang, noindex/X-Robots-Tag, internal broken links, and crawl budget limits.
7. **AEO/GEO checks:** identify public crawler directives and access errors, HTML-visible answer content, authorship/update metadata, semantic headings and structured-data validity. Do not claim that `llms.txt` or a crawler allow rule guarantees citations or AI visibility.
8. **Scoring integrity:** distinguish PASS, FAIL, WARNING and NOT TESTED; attach URL, evidence, severity, confidence and recommended action to every finding. Avoid a single score hiding a critical security issue.
9. **Persistence and reports:** keep audit records tenant-scoped; store timestamped run history and compare changes over time; redact secrets and personal data from evidence.
10. **Verification:** unit tests for every check, adversarial URL/DNS/redirect tests, tenant-isolation tests, mocked network tests, deterministic browser QA, performance/load budgets, dependency/security CI, and a controlled live test against a domain the operator is authorized to assess.

## Implementation plan (not yet executed)

1. **Completed on this branch:** direct audit API calls now return HTTP 503 after tenant authorization, before any outbound request. CI was triggered; verify its result before treating this change as validated. Keep the feature disabled until the connection-pinning fetcher is tested.
2. Implement a dedicated safe-fetch boundary, separate from SEO parsing and report scoring.
3. Expand checks in small groups: security headers/TLS; technical SEO/discovery; content/AEO readiness; performance/accessibility.
4. Add deterministic tests per finding and for hostile DNS/redirect cases before enabling any live fetch.
5. Add scan quotas, audit history and evidence-based reports.
6. Run regression, security, integration, performance, tenant-isolation and frontend QA; inspect CI on the exact commit.
7. Ask for explicit approval before merge or deployment.

## Additional source used for security criteria

- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): destination IP validation must be enforced at connection time; validating DNS and then allowing the HTTP client to resolve again is not sufficient.
- [web-recon-scanner](https://github.com/TBPH-ABD/web-recon-scanner): useful passive-check category reference for headers, TLS, cookies, forms and information disclosure.
- [recon-web](https://github.com/BrunoAFK/recon-web): broad category reference for SEO, DNS, TLS and performance, with documented DNS-pinning SSRF defenses. Its implementation and licence should be reviewed separately before reuse.
- [good-website-checklist](https://github.com/sderosiaux/good-website-checklist): checklist reference for security, SEO, AI assistants, accessibility, privacy and performance.

**Status:** Reference triage and current-code gap identification completed. A backend HTTP 503 guard was added so the disabled audit cannot be triggered through direct API calls. CI was queued at the time of this update. No third-party code copied, no audit endpoint re-enabled, no merge, and no deployment performed.
