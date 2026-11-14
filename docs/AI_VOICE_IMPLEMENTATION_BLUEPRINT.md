# AI Voice — Implementation Blueprint

Branch: `ai-voice`  
Base: `main`  
Status: implementation branch; do not merge or deploy until verification.

## Product shape

AI Voice is a focused, multi-tenant voice-agent product built on the existing AI Growth OS platform. It has three distinct experiences:

1. **Customer voice entry** — a simple public page / customer PWA with a clear call action, identity capture only where required, consent notice, and an in-browser WebRTC call. For phone-originated calls, the customer simply calls the assigned DID.
2. **Tenant workspace** — agent creation and configuration, knowledgebase management, test calls, SIP trunk/DID configuration visibility, routing, call recordings/transcripts, delivery settings and usage.
3. **Super Admin** — tenant provisioning/suspension, plan and usage controls, SIP trunk/provider administration, DID inventory and assignment, agent oversight, audit and operational health.

The existing AI Growth OS tenant and user model remains the source of truth. Every tenant-owned record must carry and be queried by `tenant_id`. Super Admin operations must be role-checked and audited.

## Existing project assets to reuse

### AI Growth OS (main + proven voice branches)

- `brain.py`: current Knowledge Brain and business-context composition. Extend it; do not replace it.
- `ai_router.py`: language detection, structured matching and FAQ/knowledge matching.
- `voice_gateway.py` / `voice_runtime.py`: provider-neutral realtime voice gateway, session state, interruption and turn tracing.
- `voice_booking_actions.py`, `booking.py`, `routing.py`: existing action and human-routing foundation.
- `call_recorder.py`, `models_calls.py`, `call_storage.py`, `routes_calls.py`: call metadata, per-turn transcript/audio capture, playback and QA.
- `voice_escalate.py`, `voice_followups.py`: escalation and follow-up behavior.
- Existing CRM, tenant auth, integrations, notifications and platform-admin provisioning.

The previously validated `feat/voice-library-brain-v2` work is a reference for proven voice behavior. Port only after comparing against this branch's current `main`; preserve existing booking/cancellation behavior and do not merge that branch blindly.

### Supplied `single-server-deploy.zip` reference

The archive contains a standalone FastAPI + React SaaS called VoiceDesk, including:
- Tenant sign-up/login and billing/usage concepts.
- Category-based agent templates, agent creation/listing, language selection and voice profiles.
- Tenant test-call and customer call-request flows.
- Call history and call detail/recording/transcript UI.
- Super Admin tenant and phone-number provisioning UI.
- Asterisk DID dialplan provisioning helper.
- Governance/authority checks, audit records and tests.

Reuse the workflows and UI concepts, not the standalone app's SQLite database/auth as a second source of truth. Its DID helper writes directly to an Asterisk dialplan and interpolates values into shell commands; that implementation must **not** be copied into production. Replace it with a validated provider adapter and controlled provisioning job. The archive has a DID-to-agent/tenant assignment concept but does not implement a complete SIP trunk lifecycle or secure SIP credential vault.

## Knowledge Brain contract (from the supplied Global Knowledge Brain specification)

Do not replace the current Knowledge Brain. Extend it with:

`CURRENT KNOWLEDGE BRAIN + GLOBAL INTENT TAXONOMY + ENTITY NORMALIZATION + STATE MACHINE + INDUSTRY TEMPLATE + KNOWLEDGE-GAP LEARNING`

Resolution order:
1. Structured tenant/business data.
2. Tenant-approved knowledge.
3. Global approved knowledge/library.
4. Model fallback only when needed and grounded by available context.
5. Clarify or human escalation when confidence/authority is insufficient.

Interpret each utterance as language → intent → topic → entities → time/date → customer state → required action → knowledge/business data → answer/action → confirmation → CRM/analytics.

Universal intent families include discover/business info, hours/location/contact, services/products/pricing, availability/booking/confirmation/rejection/cancellation/rescheduling, payment, offers/loyalty, account, orders/delivery, support/complaints, repeat/clarification, voice feedback, callback and human handoff.

Universal entities include customer, service, product, staff, department, date, time, duration, location, price, quantity, booking/order/payment identifiers and language.

Support English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Urdu and mixed Hinglish/code-switching. Normalize spoken numbers/dates/times, Indian English, filler words, acknowledgements, repetitions and ASR errors. Canonical intent and business logic remain language-independent.

Booking is a state machine. Ask only for the missing field. Check actual availability. Never invent a slot or claim confirmation before the booking backend confirms it. A new call always gets a new call/conversation context; stale booking context must not leak across calls. A bare “yes” is confirmation only when the active state explicitly awaits confirmation. Acknowledgements and voice-feedback requests must not trigger unrelated business actions or human handoff.

Unknown/low-confidence requests become knowledge-gap candidates with intent, confidence, knowledge hit, answer source, fallback, escalation and outcome. Tenant admins review and approve new knowledge before it becomes active.

## SIP trunk and DID design

Separate these concepts:
- **SIP trunk**: provider connection, authentication mode, registrar/proxy, transport, allowed codecs, inbound/outbound routing, health and registration state.
- **DID number**: E.164 number, provider/trunk association, tenant assignment, inbound agent/flow assignment, outbound caller ID policy, status and porting/provisioning state.
- **Routing**: DID → tenant → published agent/flow → voice gateway. Outbound: tenant/agent → allowed trunk → destination, with tenant permissions, rate limits, caller-ID validation and usage metering.

Credentials must be encrypted at rest and never returned in API responses or logs. Prefer provider APIs or an isolated telephony control-plane adapter. Asterisk/FreeSWITCH may be a media/telephony edge, but business logic and agent brain remain provider-neutral. Provisioning must be asynchronous, idempotent, audited and reversible. Do not run shell commands with user-controlled trunk/DID values.

Support multiple trunks and multiple DIDs per tenant; platform-owned trunk inventory may be assigned to tenants, and tenant-owned provider credentials may be supported where explicitly enabled. Keep secrets and provider-specific configuration separate from tenant-facing status.

## Recording and CRM

Every supported call channel (WebRTC and SIP/PSTN through the telephony adapter) must create a call record and associate:
- tenant, agent, DID/trunk/provider, direction, customer identity and consent metadata;
- start/end timestamps, duration, status, language, outcome and routing/handoff details;
- complete transcript and turn metadata;
- original audio recording (not only per-turn snippets), with secure private object storage;
- AI summary, intent, extracted requirements, bookings/actions, unresolved items and follow-up tasks;
- notification delivery status for email and WhatsApp.

Use private S3-compatible storage (e.g. R2/S3) in production; local disk is development-only. Audio playback must use tenant-authorized endpoints or short-lived signed URLs. Recording disclosure, consent, retention and deletion controls are required. Notification retries must be idempotent and must not interrupt calls.

## Build sequence / acceptance gates

1. Inventory existing main and voice-library branch code; identify exact call entry points and tests.
2. Add tenant-scoped agent configuration APIs and tenant UI using existing auth/roles.
3. Add Super Admin tenant/agent/DID/trunk inventory controls and audit events.
4. Add telephony adapter contracts, SIP trunk secret storage, DID mapping and provider/edge provisioning jobs.
5. Route inbound DID and outbound calls into the same provider-neutral Voice Gateway and Knowledge Brain used by WebRTC.
6. Integrate whole-call recording, CRM linking, summaries, email/WhatsApp notifications and delivery retry tracking.
7. Add tests for tenant isolation, role permissions, secrets redaction, DID routing, trunk failure/retry, call lifecycle, recording persistence, notification retries, multilingual knowledge and existing booking/cancellation regressions.
8. Run API tests, frontend build, security checks and call-path integration tests. Do not deploy to Render or merge to `main` until evidence is recorded and explicitly reviewed.

## Non-goals / guardrails

- Do not create a second tenant database or duplicate CRM.
- Do not replace `brain.py` or the existing provider-neutral voice gateway.
- Do not expose SIP passwords, provider tokens, private recordings or customer PII in public URLs.
- Do not deploy or merge automatically from this feature branch.
- Do not claim production readiness based only on unit tests or a simulated call.


## Branch progress (2026-11-14)

Committed to `ai-voice`:
- Initial SQLAlchemy records for tenant voice agents, SIP trunks and DID inventory/assignment.
- Schema registration through the existing startup migration loader.
- Tenant APIs for agent drafts/updates, SIP trunk configuration and DID-to-published-agent mapping.
- Super Admin APIs for platform trunk inventory, DID inventory, tenant agent lookup and DID assignment.
- Tenant workspace page at `/dashboard/ai-voice`.
- Super Admin control page at `/platform/ai-voice`.
- Public customer voice entry page at `/voice/[slug]`, reusing the existing VoiceCallModal/WebRTC flow.
- Navigation entries for tenant and platform workspaces.

These are configuration/control-plane foundations, not a completed telephony launch. The following are still required before a DID can carry production calls: provider-specific SIP registration and health checks; an Asterisk/FreeSWITCH or carrier edge adapter; inbound DID routing into the existing Voice Gateway; outbound trunk routing/caller-ID policy; test-call workflow; whole-call media recording from SIP/RTP; and end-to-end regression tests.

The attached VoiceDesk test suite could not be executed in this environment because its runtime dependency `razorpay` is not installed. No passing test result is claimed. The archive's original DID provisioning helper is intentionally not reused because it modifies dialplan files and shells out with interpolated values.
