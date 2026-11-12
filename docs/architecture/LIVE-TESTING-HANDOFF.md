# AI Search Visibility — Live Testing Handoff

## Current verified state
- Feature branch: `feature/aeo-geo-visibility-platform`
- Latest API regression/visibility CI: commit `3f1c7a63e767ce455579a55e269697f9243f9f42`, result **success**.
- Web build verification: commit `1774b14ebf83f29191f4d1ee757e6a759cdcb333`, result **success**.
- This confirms CI checks only; it does not prove that the hosted frontend/backend, external provider keys, OAuth, or live database have been configured.
- No changes to `main` and no production deployment were performed.

## Frontend routes
- Sign-in: `/login`
- AI Search Visibility workspace: `/dashboard/visibility`
- Integrations: use the existing app Integrations area/catalog (provider credentials and Google Search Console OAuth are managed there).
- The visibility workspace expects the existing authentication flow to set `ago_access_token` and `ago_tenant` in browser local storage. Do not bypass authentication or share a bearer token.

## Backend endpoints added/extended
- `POST /api/v1/tenants/{tenant_id}/visibility/checks/{query_id}` — run configured AI provider checks.
- `GET /api/v1/tenants/{tenant_id}/visibility/checks` — check history.
- `POST /api/v1/tenants/{tenant_id}/visibility/google-search-console/performance` — official Search Console query/page metrics.
- Existing visibility endpoints cover brand profile, competitors, tracked queries, and website audits.
- API health endpoint: `/health` (confirm actual host prefix/route from the deployed service).

## Hosting and environment prerequisites
Deploy frontend and backend from this same feature branch to a **non-production/staging** environment first. Preserve the existing application architecture. Do not deploy the feature branch to production automatically.

Frontend:
- `NEXT_PUBLIC_API_URL` = full base URL of the staging API, without an extra `/api/v1` suffix if the frontend appends that path itself.
- Configure the production/staging frontend URL in the API's `ALLOWED_ORIGINS` / allowed-origins setting so browser requests pass CORS.
- Verify the frontend build and login callback/redirect URLs against the staging domain.

Backend:
- Configure the existing database connection, signing/encryption secrets, and CORS allowlist using the repository's current deployment settings. Never commit secret values.
- Provider credentials can be entered through the tenant's existing encrypted integration configuration, or configured through the supported server environment settings.
- Providers currently supported for visibility checks: Gemini, Perplexity, Grok (xAI), and Claude (Anthropic).
- Google Search Console requires Google OAuth client ID, client secret, exact redirect URI, the `webmasters.readonly` scope, and an authenticated Google account with permission to the target Search Console property.
- A successful API CI run does not validate live provider quotas, billing, credentials, or Search Console permissions.

## How to provision login credentials safely
1. Deploy to staging and open `/login`.
2. Use the existing supported signup/onboarding flow to create a dedicated test tenant and user, or create the test user through the existing administrator process.
3. Use a unique test email address and a temporary strong password; deliver the password privately, not in this public repository or a public issue.
4. Sign in normally and verify the app establishes the tenant/session context.
5. Do not create a hard-coded demo password, bypass authentication, or seed a shared public account. No working login credentials are included in source control.

## Live test sequence
1. Sign in and confirm `/dashboard/visibility` loads without 401/403 errors.
2. Save a test brand name, domain, and description.
3. Add at least one competitor and one tracked query.
4. Configure one provider credential first; run a visibility check and verify success/failure status, evidence classification, citations, and history. Repeat for each provider only after its credentials are configured.
5. Connect Google Search Console and query a property/date range the Google account can access. Confirm query/page metrics load. These metrics are not a direct guarantee of AI Overview/AI Mode rankings.
6. Verify one tenant cannot access another tenant's data; test expired/invalid tokens and provider failures.
7. Check browser console, API logs, latency, rate-limit behavior, and persistence after a page refresh.
8. Do not declare production readiness until staging security, authorization, migration, provider-cost/rate-limit, and performance checks are recorded as passed.

## Explicitly out of scope / still pending
- Website audit hardening remains separate and is not represented as complete.
- Hermes orchestration integration is deferred; it is not an AI search provider adapter and was not added to avoid expanding/changing the existing architecture.
- Live provider calls, Google OAuth, and deployment-specific login credentials remain unverified until staging hosting and secrets are configured.
- Production release remains **NO-GO** until the above live checks and release gates pass.
