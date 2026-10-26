# P1 GitHub closeout

This checklist is for the isolated branch `feat/p1-closeout-support-alerts-verification`.
It deliberately does not claim production verification and does not change deployment settings.

## 1. Team Communications

- [ ] Reconcile `feat/tenant-comms-whatsapp-capabilities` against `main`; review both sides of the one-ahead/one-behind divergence before merging.
- [ ] Decide and implement true shared department/group rooms with persisted membership; the current multi-recipient selector sends individual copies and is not a shared group room.
- [ ] Test direct-message visibility in both directions and ensure no cross-tenant reads/writes.
- [ ] Test attachment authorization, upload/download, allowed MIME types, size limits, and voice-note recording/playback.
- [ ] Test role-based permissions and staff access provisioning.

## 2. Support tickets and escalation

Existing implementation found on `main`: tenant-authenticated ticket list/create/reply routes and platform-admin list/get/create/status/assign/reply routes; SLA and audit logging exist in `apps/api/app/tickets.py`.

- [ ] Add and test customer-facing ticket creation from the tenant/customer PWA without requiring an admin login.
- [ ] Persist department routing and reassignment/forwarding history.
- [ ] Add controlled escalation from a ticket to the appropriate persistent team room, preserving ticket ID and links.
- [ ] Verify ticket remains open until explicitly resolved/closed and reply transitions are correct.
- [ ] Test authorization and tenant isolation on every ticket operation.

## 3. Booking and order alerts

- [ ] Identify the canonical persisted appointment/order creation and status-change paths.
- [ ] Emit durable alerts only after a successful database commit; do not treat a voice/UI confirmation as persistence evidence.
- [ ] Resolve recipients from tenant-configured staff/department/role settings, not hard-coded recipients.
- [ ] Persist delivery attempts/results and handle provider-not-configured/failure states without losing the underlying booking/order.
- [ ] Test appointment creation, order creation, status changes, duplicate events, and cross-tenant isolation.

## 4. Production verification (GitHub-side gates only here)

- [ ] CI passes on the final PR head (API tests, compile/import checks, frontend build, and focused regression tests).
- [ ] Cancellation flow is unchanged and existing cancellation tests pass.
- [ ] PR diff reviewed for tenant isolation, authorization, migrations, and accidental secrets.
- [ ] Render deployment and live health are intentionally excluded from this GitHub-only checklist; verify separately after code is approved.

## Closure policy

Do not mark an item complete from code presence alone. Attach test results to the PR. Do not merge to `main` or trigger a deployment without explicit approval.