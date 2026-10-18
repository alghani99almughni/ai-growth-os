# AEO/GEO Visibility — Security and Reliability Gates

## Authentication and authorization
- Require the existing authenticated user dependency for every tenant endpoint.
- Reuse the platform's tenant authorization helper; never rely only on a path parameter.
- Platform-admin operations must use the existing platform-admin guard.
- Add tests proving Tenant A cannot read, update, delete, export, or infer Tenant B's records.

## SSRF-safe website auditing
User-supplied URLs are untrusted. Before every outbound request:
1. Accept only HTTP/HTTPS.
2. Reject credentials in URLs and unsupported ports.
3. Resolve hostnames and reject loopback, private, link-local, multicast, reserved, and metadata-service IP ranges for IPv4 and IPv6.
4. Validate every resolved address and every redirect target; limit redirects.
5. Protect against DNS rebinding by connecting only to a validated destination where the HTTP client permits it.
6. Set strict connection/read timeouts, response-size caps, page-count caps, and content-type allowlists.
7. Do not execute downloaded scripts or render arbitrary HTML in a privileged browser.
8. Avoid fetching internal network destinations, cloud metadata endpoints, local files, or non-HTTP schemes.
9. Apply per-tenant and global rate limits.
10. Log safe error codes without credentials or sensitive response bodies.

## Provider secrets
- Reuse the existing encrypted integration credential model and provider abstractions.
- Never return secret values in status or API responses.
- Keep keys server-side; do not place provider credentials in browser bundles, logs, reports, or URLs.
- Respect provider terms, rate limits, and availability. Do not scrape private or authenticated content.

## Reliability
- Long-running jobs need explicit states: queued, running, completed, partial, failed.
- Use bounded retries with backoff only for transient failures.
- Make retries idempotent and avoid duplicate usage billing.
- Persist provider errors and timing metrics; avoid logging raw prompts/responses if not necessary.
- If the existing job infrastructure is insufficient, document the gap before selecting a queue.
- Keep audit and visibility checks separate so one provider outage does not erase other results.
- Expose readiness/health without leaking credentials or tenant data.

## Truthfulness and reporting
- Keep method/provider/model/version/time metadata for every observation.
- Distinguish a live search-grounded observation from a model-only sample and from a website audit.
- Show coverage, sample count, last successful check, and failure/partial status.
- Do not claim guaranteed rankings or fabricate citations.
- Recommendations should link back to a finding or observation.

## Required tests before merge
- Tenant isolation for every new resource.
- URL validation: localhost, private IP, IPv6 loopback, metadata endpoints, redirects to private IP, non-HTTP scheme, DNS rebinding considerations, oversized responses, timeout.
- Provider failure, rate limit, malformed response, and missing credentials.
- Retry/idempotency and duplicate usage accounting.
- Empty dataset and partial-run dashboard states.
- Existing API and frontend regression tests.
- Migration upgrade and rollback against a disposable database.

## Release gates
1. Code review completed.
2. Unit and integration tests pass.
3. Security checks pass.
4. Database migration and rollback verified, if applicable.
5. Build and deployment preview succeed without production side effects.
6. Manual tenant-isolation smoke test passes.
7. Explicit approval before merge/deploy.
