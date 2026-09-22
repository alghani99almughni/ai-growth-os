# AI Growth OS — Error & Recovery Log

**Purpose:** Recovery knowledge base for future agents/CTO sessions. Before changing production, search this document for the symptom/error and follow the recorded fix and verification path.

## Recovery rules
- Do not create duplicate Render services, databases, or Redis instances when an existing AI Growth OS resource already exists.
- Treat `ai-growth-os-web`, `ai-growth-os-api`, `ai-growth-os-db`, and `ai-growth-os-redis` as the production resources unless the platform state explicitly changes.
- Verify GitHub, Render deploy state, API health, and browser behavior before declaring a fix complete.
- Never store plaintext passwords or API secrets in source control, logs, or customer records.

## Incident 001 — Gemini model not found
**Symptom:** Gemini integration failed with v1beta model-not-found errors using the old `gemini-pro` configuration.

**Root cause:** The integration was using an outdated model/API path.

**What we did:**
- Installed `google-genai`.
- Moved the AI service to the current Google GenAI SDK.
- Tested the integration with available Gemini models.
- Confirmed a direct Gemini test returned a valid response.

**Recovery:** Use `google-genai` and a currently available model configured through environment settings. Do not hard-code the retired `gemini-pro` model.

## Incident 002 — OpenRouter free model / credit mismatch
**Symptom:** Some OpenRouter models rejected requests because the requested token budget exceeded available credits; other free model routes worked.

**Root cause:** Model availability, credit limits, privacy/guardrail settings, and maximum token budgets vary by provider/model.

**What we did:**
- Tested provider authentication.
- Verified a Qwen coder route could return a successful response.
- Reduced model-specific `max_tokens` where necessary.

**Recovery:** Verify the exact provider/model and available limits before changing application code. Do not assume a model advertised as free has unlimited tokens.

## Incident 003 — Render Blueprint validation: Key Value IP allow list
**Symptom:** Render rejected `render.yaml` with `services[2] must specify ip allow list`.

**Root cause:** The Render Key Value resource required an explicit IP allow list in the Blueprint specification.

**What we did:** Added:
```yaml
ipAllowList:
  - source: 0.0.0.0/32
    description: Block public internet access; API uses Render private networking
```
under `ai-growth-os-redis`.

**Commit:** `b821920af89126ba96513dadecfe18b6223a4801`

**Recovery:** Keep the Key Value IP allow list explicit when using this Render Blueprint.

## Incident 004 — Render API boot failure from literal database references
**Symptom:** SQLAlchemy attempted to parse values such as `${{ai-growth-os-db.DATABASE_URL}}` and `${{ai-growth-os-db.connectionString}}` as database URLs.

**Root cause:** Environment-variable expressions were being stored literally instead of being resolved by the Render Blueprint.

**What we did:**
- Associated existing resources with the Render Blueprint through Render's Blueprint flow.
- Used `fromDatabase` / `fromService` wiring in `render.yaml`.
- Avoided treating literal `${{...}}` values as runtime database URLs.

**Recovery:** If the API log shows `${{...}}` inside a database/Redis URL, inspect the Render Blueprint wiring first. Do not hard-code the resolved secret into GitHub.

## Incident 005 — Render Postgres driver incompatibility
**Symptom:** API startup failed because the Render Postgres URL used the generic `postgresql://` scheme while the container installed `psycopg` v3.

**Root cause:** SQLAlchemy needed an explicit psycopg v3 dialect.

**What we did:** Updated `apps/api/app/db.py` to normalize:
- `postgres://` → `postgresql+psycopg://`
- `postgresql://` → `postgresql+psycopg://`

**Commit:** `0977d65644b8afefecb91fb97953a457af7b81cf`

**Verification:** Render API reached startup complete, Uvicorn bound to port 10000, and `/health` returned 200.

**Recovery:** Preserve this normalization unless the database driver changes.

## Incident 006 — Platform admin login failed response validation
**Symptom:** Super Admin login reached the API but auth response validation failed because the internal platform tenant slug was `__platform__`.

**Root cause:** `TenantOut` only accepted URL-safe hyphenated slugs, while the internal platform tenant uses underscores.

**What we did:** Relaxed only the output schema to allow `^[a-z0-9_-]+$`, while normal tenant creation remains restricted to `^[a-z0-9-]+$`.

**Commit:** `9f3a3dd2d7e83f3924a962ae8c3d3e551ac1e`

**Recovery:** Keep the internal platform slug exception limited to output/auth responses.

## Incident 007 — SS Nutritions customer voice modal exposed implementation details
**Symptom:** Customer UI displayed technical text such as `PRIVATE IN-PWA CALL`, browser microphone details, and AI-agent implementation wording.

**Root cause:** Internal implementation language was exposed in customer-facing UI.

**What we did:** Changed the customer copy to:
- `Talk to SS Nutritions`
- `Please enter your name and mobile number.`
- `Start call`

Also changed customer-facing `Call AI` labels to `Call us`.

**Recovery:** Customer UI must describe the business experience, not the underlying PWA/WebSocket/AI implementation.

## Incident 008 — SS Nutritions / Business not found
**Symptom:** Customer call modal returned `Business not found` on the deployed SS Nutritions PWA.

**Root cause:** The frontend used a hard-coded `ss-nutritions` path while tenant resolution could differ after provisioning.

**What we did:**
- Added public business resolution by normalized business name.
- Frontend resolves the tenant first and uses the returned slug for website/call APIs.
- Added dynamic `/pwa/[slug]` routing and tenant manifest generation.

**Recovery:** Customer-facing tenant routes must resolve the active tenant rather than assume a hard-coded tenant slug.

## Incident 009 — Tenant PWA architecture correction
**Symptom:** The requirement was that every onboarded tenant receive its own category-based PWA.

**What we did:**
- Added dynamic tenant PWA route `/pwa/{tenant-slug}`.
- Added dynamic tenant PWA manifest route.
- Changed QR generation to point to `/pwa/{tenant-slug}?qr=...`.
- Changed onboarding to generate a business QR entry immediately after tenant creation.
- Added industry feature templates so tenants inherit category-specific defaults.

**Known follow-up:** The current PWA route is a wrapper around the customer engine and still needs final tenant-specific branding/icon generation and full installability validation.

## Incident 010 — Platform page client-side exception
**Symptom:** `/platform` displayed `Application error: a client-side exception has occurred` while the Render web service remained healthy.

**Initial finding:** Render showed a healthy Next.js process and no server crash. The page had unhandled client-side fetch/JSON failures.

**Recovery path:** Make platform data loading defensive (`try/catch`, status checks, safe JSON parsing, auth redirect) and verify the deployed browser bundle after deployment. Do not create another Render service.

## Incident 011 — Onboarding credentials / confirmation notifications
**Requirement:** After Super Admin provisions a tenant, our platform should send confirmation by email and WhatsApp, including the owner login information. Owners must also have a secure password reset path if they forget the password. The credential UI must include a show/hide password preview so the admin can verify what was entered.

**Security rule:** Passwords are stored only as hashes. Initial credentials should be treated as temporary and resettable. Password reset must use a time-limited, single-use token rather than exposing the stored password.

**Implementation target:**
- Platform notification service with configurable email provider and platform WhatsApp provider.
- Provisioning response includes notification delivery status, not provider secrets.
- Super Admin provisioning form has show/hide password control and clear validation.
- Owner login has `Forgot password?`.
- Reset request sends a time-limited reset link/code through configured channels.
- Reset endpoint invalidates the token after use and replaces the password hash.
- Notification failures must not silently make tenant provisioning look failed; tenant creation remains successful and admin sees delivery status.

## Current production tenant
- SS Nutritions is activated.
- Owner login: `ssnutritionmnb@gmail.com`.
- Do not record or commit the owner's password in this log.

## Future agent checklist
1. Search this file for the exact Render/API/browser error.
2. Inspect the current GitHub commit before reverting anything.
3. Inspect current Render deploy/log/health state.
4. Preserve existing production resources.
5. Patch the smallest root cause.
6. Deploy through the existing Render auto-deploy/Blueprint setup.
7. Verify API `/health`, authentication, affected UI, and the relevant end-to-end flow.
8. Append the new incident, root cause, fix, commit, and verification result to this log.


## Incident 012 — Reset-password page failed Next.js production build
**Symptom:** Render web build failed with `useSearchParams() should be wrapped in a suspense boundary at page "/reset-password"`.

**Root cause:** The new reset page read the URL query using `useSearchParams()` without a Suspense boundary.

**What we did:** Replaced `useSearchParams()` with client-side `window.location.search` parsing inside `useEffect()`.

**Commit:** `88bfcf0b8c8f164476bcb809d911fb934e63280c`

**Recovery:** For simple client-only query parameters, parse the browser URL in an effect or explicitly wrap `useSearchParams()` in Suspense.

## Incident 013 — Platform notification and credential recovery implementation
**What we did:**
- Added platform email/WhatsApp notification service.
- Tenant provisioning now attempts owner confirmation with business name, login email, temporary password and login URL.
- Added notification delivery status to the Super Admin provisioning result.
- Added Super Admin password show/hide preview and minimum-length validation.
- Added `Forgot password?` to login.
- Added secure, time-limited, single-use password reset tokens stored as hashes.
- Added `/forgot-password` and `/reset-password` pages.
- Added Render Blueprint environment declarations for notification providers.

**Configuration:** Email requires a configured Resend API key and sender address. Platform WhatsApp requires configured OpenWA or Meta credentials. Until configured, delivery status is `not_configured`; the platform does not claim delivery.

**Security:** Passwords and reset tokens are stored only as hashes. The initial temporary password is not written to this recovery log.

## Current deployment state
The latest API/web commits were queued or in progress when this entry was written. Do not call the notification/reset feature fully production-verified until the latest deployments are `live` and the end-to-end flows have been tested.


## 2026-09-22 — main.py entrypoint truncation after password-reset change
- **Symptom:** Render API deploy failed with `IndentationError: expected an indented block after function definition`; the file ended at an incomplete `create_feedback` function before later recovery endpoints.
- **Root cause:** A file update replaced/truncated the API entrypoint while attempting to modify imports/model wiring.
- **Recovery:** Restored `apps/api/app/main.py` from the last known-good commit before the truncation, then layered password-reset and knowledge/CRM changes onto the complete entrypoint.
- **Prevention:** Never patch a large entrypoint from a partial file response. Fetch/reconstruct the full file, preserve the known-good revision, and verify Python syntax before deployment.

## 2026-09-22 — knowledge-first voice architecture
- **Requirement:** Common questions should be answered from the approved knowledge library without invoking the AI agent; only exceptions should use AI tokens.
- **Implementation:** Added approval-aware tenant knowledge retrieval, learned-question candidates, usage counters, multilingual metadata, PWA speech-recognition routing, and AI/human escalation telemetry.
- **Safety:** AI-generated answers are stored as reviewable candidates first; they are not automatically promoted to permanent tenant knowledge.

## 2026-09-22 — CRM voice intelligence
- **Implementation:** PWA calls now have call number, start/answer/end timestamps, duration, language, resolution, knowledge-hit count, AI-turn count, transcript, and human-callback flag.
- **Recovery path:** unresolved voice turns mark the call for human callback and route it through the existing staff routing system.
