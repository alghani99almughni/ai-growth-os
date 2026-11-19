# AI Voice — Customer Journey, CRM, Call Transcription & Messaging Specification

Status: implementation specification for the standalone `ai-voice` product.
Branch: `ai-voice-customer-crm-flow`.
Scope: standalone AI Voice only. Never connect to or deploy against the existing AI Growth OS production database, Redis, API, or frontend.

## Non-negotiable acceptance rule

**Every call must produce a durable, searchable text transcript in the tenant CRM.** Audio recording is an additional asset, not a substitute for the transcript. A call must still have a call record and transcript status when audio recording fails. Never mark a transcript complete unless the text was actually persisted.

For every recognized customer utterance and every AI response, persist an ordered turn with:
- call_id, tenant_id, customer_id when known, turn number
- speaker (customer, assistant, staff, system)
- exact recognized/displayed text (do not silently paraphrase the transcript)
- language, event timestamp in UTC, tenant timezone for display
- STT/TTS/provider metadata and error state where applicable
- linked booking_id/order_id/callback_id when the turn creates or changes one

Persist partial/final transcription status explicitly. Final utterances are mandatory transcript entries. If STT fails or the call contains unintelligible speech, persist an explicit transcription-gap marker with timestamp and reason; do not fabricate words. Persist assistant speech text even if TTS audio fails.

## 1. Customer entry and identity

Supported entry points: inbound voice/PSTN when carrier routing is configured, browser WebRTC voice link, WhatsApp, website/PWA, and email. Resolve tenant/business before resolving a customer. All identity matching is tenant-scoped.

Normalize phone numbers to E.164 where possible. Match verified phone/channel identifiers first. Caller ID is a matching hint, not proof of identity. A shared, hidden, changed, or unverified number requires a confirmation/verification step before revealing private booking/order information or modifying records. Do not auto-merge on name similarity alone.

New customer: create one customer profile, collect name and contact details progressively, capture applicable consents.
Returning customer: reuse the existing profile, load relevant open bookings/orders and preferences, and avoid asking for information already verified.
Different tenant + same phone: always separate tenant customer records.

## 2. Unified customer profile

One tenant-scoped customer profile is the parent for:
- customer identifiers and verification states
- communication and recording consent/preferences
- interactions across voice, WhatsApp, web/PWA and email
- calls, recordings, transcripts and summaries
- bookings and immutable booking event history
- orders, line items, payment and fulfilment history
- outbound notifications and provider delivery receipts
- staff/AI audit events

Customer 360 must show a chronological timeline with links to the original call, transcript, booking/order and messages.

## 3. Call lifecycle and text transcript

Create the call record as early as possible (including missed, abandoned, failed and transferred calls). Record tenant, channel, direction, start/end timestamps, timezone, caller identity evidence, customer match status, language, duration, outcome, transfer/callback status and recording/transcription status.

For each conversation turn:
1. Save the final customer STT text.
2. Save the AI/staff response text.
3. Link the turn to the call and customer.
4. Attach detected intent/entities and any transaction IDs.
5. Commit durable text before reporting the action as complete.

The transcript view must be readable as a speaker-labelled conversation, searchable by text, filterable by tenant/customer/date/outcome, and exportable by authorised users. Access is tenant-scoped and role-controlled. Keep recording consent and retention policy separate from transcript retention policy. Apply configured retention/deletion rules and audit access.

A call with no speech still has a call record and a clear outcome. A call with STT outage has a transcript gap event and error metadata. Never drop the entire call because an audio file could not be stored.

## 4. Booking workflow

Intent → identify/verify customer → service/staff/location → requested date/time → check tenant timezone, opening hours, staff/resource availability and booking rules → clarify ambiguous AM/PM → read back full date/time → explicit customer confirmation → persist booking → persist booking event → queue notifications.

Use the actual call-start timestamp and tenant timezone as the reference for relative dates. Never silently infer AM/PM. For 24/7 tenants, AM/PM clarification is mandatory for ambiguous clock times. Recheck slot availability immediately before committing.

Booking states include requested, pending_confirmation, confirmed, reschedule_pending, cancelled, completed, no_show, rejected and expired as applicable. Enforce valid transitions.

## 5. Repeat calls, reschedule and cancellation

A repeat caller must resolve to the same customer profile when identity evidence is sufficient. Retrieve the existing booking rather than creating a duplicate.

Rescheduling preserves the booking identity where the business workflow permits it, and appends an immutable event containing previous slot, new slot, reason, actor, call_id and timestamp. Cancellation records who requested it, reason, policy result, effective timestamp and originating call_id. Repeated requests against an already-cancelled or already-rescheduled record must be idempotent and must not duplicate notifications or events.

If customer requests a fresh booking after cancellation, create a new booking linked to the same customer and retain the cancelled booking history. Reinstatement is allowed only if tenant policy permits it.

## 6. Order workflow

Identify/verify customer → resolve product/service catalogue → validate availability and current price → capture quantity/options → delivery or pickup → capture/confirm address if needed → read back itemised total → explicit confirmation → create order and order items → payment workflow/status → fulfilment updates.

Never invent stock, price, discount, tax, payment success or delivery status. Order updates are appended to an order event history and linked to the call that requested or caused the change.

## 7. WhatsApp and email event triggers

Trigger notifications from committed CRM/business events, not from unverified AI dialogue. Use an outbox/queue with idempotency keys, provider message IDs, attempts, timestamps and delivery status.

Transactional triggers:
- booking confirmed, rescheduled, cancelled, reminder
- order confirmed, payment status/receipt, dispatched, ready for pickup, delivered/completed
- callback request acknowledgement and callback outcome where configured

Use tenant-approved templates and configured provider credentials. Respect channel availability, customer preferences, applicable consent and opt-out rules. Promotional messages require separate marketing consent. Record queued, sent, delivered, read (if provider supports), failed and retry states. Failed delivery must be visible in CRM; retry safely and avoid duplicate sends. Never claim delivered based only on an API request being accepted.

## 8. Data model / relationships

Minimum logical records:
- customers
- customer_identifiers
- customer_consents
- interactions
- calls
- call_turns / transcript_segments
- call_recordings (audio metadata and secure storage reference)
- bookings
- booking_events
- orders
- order_items
- order_events
- payments
- notifications / message_outbox
- audit_logs

Every tenant-owned row must be tenant-scoped and protected by backend authorization. Call turns, bookings, orders and notifications must link back to the customer and originating interaction/call where applicable. Use foreign keys, indexes and idempotency constraints for transaction safety.

## 9. AI Growth OS reuse policy — copy only after verification

Potential reuse candidates found on the `ai-voice` branch:
- `apps/api/app/models_calls.py` — relational call and turn models; CallTurn already has customer_text and ai_text fields.
- `apps/api/app/call_recorder.py` — per-call recorder; writes customer and AI text into CallTurn.
- `apps/api/app/routes_calls.py` — tenant-scoped call list/detail/audio APIs; tenant resolution and authentication must be reviewed before reuse.
- `apps/api/app/call_storage.py` — local/S3-compatible audio storage adapter; production persistence configuration must be verified.
- `apps/api/app/voice_bot.py` — invokes CallRecorder for final customer utterances and AI replies in its server-side bot path.
- `apps/web/components/CallsPanel.tsx`, `apps/web/components/CrmPanel.tsx`, `apps/web/app/dashboard/crm/[id]/page.tsx` — candidate dashboard components/pages, but not yet proven compatible with the standalone frontend.
- `apps/web/app/voice/[slug]/page.tsx` and `apps/web/components/VoiceCallModal.tsx` — candidate public browser voice flow, but they currently live in the main web app, not the standalone Next.js app.

**Do not copy a file merely because it exists.** Before copying, run its relevant tests, inspect its imports/dependencies, verify tenant isolation and verify that its runtime path is actually used. Do not copy the main app's configuration, secrets, database settings, auth bypasses, tenant data, or production integrations. Prefer shared API modules already packaged by the standalone Docker build; copy UI files only after adapting and building them inside the standalone app.

## 10. Release acceptance tests

1. New customer call: customer profile + call + speaker-labelled text transcript persisted.
2. Returning caller: same customer reused; no duplicate profile.
3. Same phone in two tenants: separate customer profiles and no cross-tenant visibility.
4. Call with no audio recording: call and text transcript still persist.
5. STT failure: call persists with explicit transcript gap; no fabricated transcript.
6. AI response: assistant text saved even if TTS fails.
7. Booking created: transcript, call, customer, booking and confirmation notification are linked.
8. Reschedule: same booking history preserved; previous/new slot and source call linked.
9. Repeated cancellation: idempotent; no duplicate cancellation event or message.
10. New booking after cancellation: new booking ID, same customer profile.
11. Order created/updated: order events and originating calls linked.
12. WhatsApp/email provider failure: failure persisted, safe retry, no duplicate sends.
13. Tenant isolation: API and UI cannot read another tenant's calls, transcripts, recordings, bookings, orders or notifications.
14. Missed, abandoned, transferred and callback calls all appear in the CRM interaction timeline.
15. Transcript search, pagination and authorised export work for long call histories.

## 11. Launch blockers that require real environment validation

A passing health endpoint is not proof of a working call path. Before launch, validate dedicated database and Redis connectivity, schema migrations, persistent recording storage, STT/TTS runtime, actual browser call, carrier route if PSTN is advertised, credentials/first admin provisioning, provider notifications, tenant isolation and the complete end-to-end acceptance suite. Do not claim production-ready until evidence exists.
