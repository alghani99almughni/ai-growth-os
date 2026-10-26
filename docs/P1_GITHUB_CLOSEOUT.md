# P1 closeout status

Branch: `feat/p1-closeout-support-alerts-verification`

## Implemented on this branch (not yet production-verified)

### Team Communications
- Added persisted private group rooms and room-member records.
- Added create/list room APIs; non-default room history and sends require active membership in the same tenant.
- Added group-room selection and creation UI in Team Communications.
- Existing direct messages, attachment controls, role checks, and preferences remain in place.

### Support tickets and escalation
- Added persistent escalation history with tenant-scoped list endpoint.
- Added tenant ticket escalation endpoint with same-tenant department/staff validation, assignment, status transition, and targeted operational alerts.
- Ticket create, reply, and status changes now create operational inbox alerts.
- Existing SLA and audit logging remains in place; cancellation/appointment cancellation code was not edited.

### Booking and order alerts
- Added durable per-user operational alerts and tenant-scoped list/read APIs.
- New appointments create alerts in the same DB transaction as the appointment.
- New orders create alerts in the order transaction.
- Recipients include tenant admins plus assigned staff or matching active operational departments (booking/reception/front desk/appointment or order/kitchen/operations).
- Added an operational alerts bell/inbox to the tenant dashboard. Alerts are in-app inbox notifications; this branch does not claim email, SMS, or push delivery.

## Required verification before calling these P1 items closed
- [ ] GitHub Actions API tests and compile checks pass on the final head.
- [ ] Frontend production build passes.
- [ ] Verify private room membership, direct messages, attachments, and cross-tenant authorization.
- [ ] Verify ticket escalation history, status transitions, SLA behavior, and tenant isolation.
- [ ] Verify appointment/order alerts, recipient routing, read/unread state, and duplicate/error behavior.
- [ ] Run cancellation regression tests and confirm the cancellation flow is unchanged.
- [ ] Review final PR diff and security/migration implications.

Production/Render checks are intentionally excluded per user instruction. Do not merge or deploy without explicit approval.