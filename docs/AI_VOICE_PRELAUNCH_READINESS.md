# AI Voice Prelaunch Readiness

Branch: `ai-voice` only  
Production deployment: NOT APPROVED / NOT STARTED  
Existing AI Growth OS services: MUST NOT BE MODIFIED

## Scope

Standalone AI Voice SaaS with one combined Render web service (Next.js + FastAPI), a dedicated PostgreSQL database and Redis. Free/Paid are client plans. Super Admin retains Free/Paid/DID-SIP controls. The Super Admin Conversation Hub and review-first Knowledge Agent are part of the product.

## Implemented in source (not yet production-verified)

- Standalone landing page, shared login, tenant workspace and Super Admin workspace.
- Super Admin Conversation Hub page at `/platform/ai-voice/learning`.
- Platform-admin-only APIs to list call conversations, view transcript details, process completed transcripts, list pending knowledge candidates, and approve/reject candidates.
- Deterministic transcript parser extracts CUSTOMER/AI question-answer pairs into pending candidates without calling a paid model API.
- Completed browser voice call finalizer attempts transcript processing.
- Approved candidate is written to the matching tenant's KnowledgeItem; tenant_id is preserved.
- Super Admin workspace links to Conversation Hub.
- Voice booking now has a deterministic AM/PM resolver that uses the persisted UTC call-start timestamp converted to tenant-local time, tenant business hours and the customer-only transcript.
- Relative appointment dates are re-resolved server-side from the most recent customer date utterance using the call-start date; booking rechecks live availability and staff before commit.

## Mandatory prelaunch gates

### A. Build and API integrity
- [ ] Confirm branch HEAD and inspect all latest commits.
- [ ] GitHub Actions standalone frontend build passes.
- [ ] Combined Docker image builds, including FastAPI import/route smoke test.
- [ ] Run API unit tests and focused Knowledge Agent tests.
- [ ] Verify all new API routes are registered and platform-admin authorization is enforced.
- [ ] Verify migrations/schema support KnowledgeCandidate, KnowledgeItem and InteractionEvent in a fresh database.

### Booking interpretation and final availability
- [ ] GitHub Actions booking-time unit tests pass on the latest ai-voice commit.
- [ ] Browser E2E verifies call-start timezone conversion, today/tomorrow/weekdays, explicit AM/PM, ambiguous AM/PM, 24/7 clarification and standalone AM/PM follow-up.
- [ ] New booking and rescheduling both use the call-start timestamp and tenant hours.
- [ ] Availability is checked before read-back and rechecked after customer confirmation; concurrent booking conflict is rejected.
- [ ] Verify overnight hours, cross-midnight slots, all-day hours and same-day past-time rejection.

### B. Conversation capture and learning
- [ ] Verify browser voice call transcripts persist every customer and AI turn.
- [ ] Verify calls with no transcript are safely ignored.
- [ ] Verify multilingual transcript handling and role labels.
- [ ] Verify agent processing is idempotent and retry-safe.
- [ ] Verify processing failures do not terminate or corrupt a call.
- [ ] Verify candidate deduplication and repeat-question counts.
- [ ] Verify AI-generated answers remain unverified until Super Admin approval.
- [ ] Verify approve/reject actions, audit trail, and tenant assignment.
- [ ] Verify tenant A's approved knowledge is never retrieved by tenant B.
- [ ] Verify only approved knowledge is used by future call retrieval.
- [ ] Verify retention, access controls and redaction policy for phone numbers and sensitive transcript content.

### C. Knowledge Agent operational readiness
- [ ] Move transcript analysis to a durable background worker/queue; do not rely solely on work inside the WebSocket finalizer.
- [ ] Add retry/dead-letter handling and processing status visibility.
- [ ] Add review/edit workflow before approval.
- [ ] Add human-corrected answers and verified source precedence; never promote an AI answer as fact merely because it appeared in a transcript.
- [ ] Add evidence/provenance: source call, tenant, language, timestamp, reviewer and approval time.
- [ ] Confirm how non-voice conversations are captured if they are in launch scope.

### D. Voice plans and runtime
- [ ] Free complete call uses local STT, local LLM and local TTS; prove no paid AI inference provider is called.
- [ ] Paid plan provider activation, credential handling, usage limits and billing enforcement pass tests.
- [ ] Browser WebRTC call, reconnect, inactivity timeout, call completion and transcript persistence pass end-to-end tests.
- [ ] Whole-call audio recording and CRM linkage are verified or explicitly excluded from initial launch.
- [ ] Human handoff and callback flows pass tests.
- [ ] DID/SIP remains Super Admin-only; carrier registration and real inbound/outbound routing are verified or explicitly excluded from initial launch.

### E. Dedicated Render environment
- [ ] Inspect Blueprint plan before applying; it must create only the new AI Voice web service, dedicated DB and dedicated Redis.
- [ ] Confirm no existing Render resource is updated, replaced or deleted.
- [ ] Configure secrets directly in Render; never paste secrets into chat or commit them.
- [ ] Verify `/health`, `/ready`, login, role routing, database/Redis connectivity and WebSocket proxy.
- [ ] Verify tenant isolation with at least two test tenants.
- [ ] Run smoke tests after deployment.
- [ ] Obtain explicit user approval before creating resources or deploying.

## Current limitations to disclose

- The current Knowledge Agent is a deterministic transcript Q/A extractor, not yet a continuously running autonomous background worker.
- It uses transcript AI responses as unverified candidate material; Super Admin must verify/edit before approval.
- The Super Admin Conversation Hub currently lists voice CallRecord transcripts, not every channel's conversation history.
- The booking-time resolver has 17/17 isolated logic checks in a local harness; this is not a GitHub Actions result or browser E2E evidence. The latest GitHub commit has no reported status checks yet.
- Source-level implementation outside those isolated checks has not yet been proven by a passing CI run or end-to-end test.
- Free zero-paid-AI-token voice calls, whole-call recording/CRM, and live DID/SIP routing remain separate production gates.

## Release rule

Do not call AI Voice production-ready, onboard paying clients, or claim the Free zero-paid-AI-token path is verified until the applicable gates above have evidence. Work only on `ai-voice`; never merge to `main` or touch existing AI Growth OS production services without separate explicit authorization.
