# P1 closeout status

Branch: `feat/p1-closeout-support-alerts-verification`

## Implemented on this branch

### Team Communications
- Added persisted private group rooms and room-member records.
- Added create/list room APIs; non-default room history and sends require active membership in the same tenant.
- Added group-room selection and creation UI in Team Communications.
- Existing direct messages, attachment controls, role checks, and preferences remain in place.

### Support tickets and escalation
- Added customer-facing support-ticket submission in the customer experience/PWA with name, phone, subject and message.
- Added public ticket API scoped by business slug and the tenant's support-ticket feature setting.
- Added persistent escalation history and tenant-scoped escalation endpoint with same-tenant department/staff validation.
- Escalations can post a ticket reference and reason into a selected authorized shared team room; optional staff assignment must be a room member.
- Escalating a resolved/closed ticket reopens it to `in_progress`.
- Ticket creation, replies, status changes and escalations generate in-app operational alerts.
- Existing SLA and audit logging remain in place.

### Booking and order alerts
- Added durable per-user operational alerts and tenant-scoped list/read APIs.
- New appointments create alerts in the same DB transaction as the appointment.
- New orders create alerts in the order transaction.
- Non-cancellation appointment/order status changes create alerts after the source change is committed.
- Recipients include tenant admins plus assigned staff or matching active operational departments (booking/reception/front desk/appointment or order/kitchen/operations).
- Added an operational alerts bell/inbox to the tenant dashboard. Alerts are in-app inbox notifications; email/SMS/push delivery is not claimed.
- Cancellation behavior was not intentionally changed; cancellation status changes are excluded from new status-alert generation.

## Verification

Latest code commit verified by GitHub Actions:
- CI: backend compile and frontend production build passed.
- API test workflow passed.
- Deterministic voice regression passed.

Additional pre-merge review gates:
- [ ] Manually exercise private room membership and cross-tenant authorization with two real tenant accounts.
- [ ] Exercise customer ticket submission, escalation routing/history and SLA handling against a disposable test tenant.
- [ ] Exercise appointment/order create and status alerts, recipient routing, and read/unread state against a disposable test tenant.
- [ ] Review final diff for authorization and migration implications.

Production/Render checks are intentionally excluded per user instruction. Do not merge or deploy without explicit approval.
