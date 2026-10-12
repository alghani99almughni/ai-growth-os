# Security & Visitor Management

Optional AI Growth OS module for School, Apartment, and Hospital tenants.

## Initial scope
- Visitor registration and tenant-bound QR gate passes
- Approval workflow with explicit authorized human approval
- Check-in/check-out and append-only audit events
- Vehicle details and optional Google Drive snapshots
- Tenant-scoped settings and role enforcement
- Optional Google Sheets/Drive compatibility adapter for SmartCheck migration
- AI chat and voice can collect visitor details, answer policy questions, and initiate requests; they cannot independently grant access

## Security requirements
- Derive tenant access from the authenticated principal; do not trust client-supplied tenant IDs alone.
- Enforce module entitlement, tenant membership, and role permissions server-side for every operation.
- Hash unpredictable QR tokens at rest; enforce expiry and single-use/replay rules.
- Store integration credentials server-side, encrypted; never expose them to browser or Android clients.
- Record approvals and entry/exit transitions in an append-only event history.
- Test cross-tenant access denial and duplicate requests before production.

## Delivery sequence
1. Backend models and migration.
2. Authenticated, tenant-scoped visitor APIs and state transitions.
3. Tenant and Super Admin UI.
4. Google Sheets/Drive adapter.
5. Chat/voice workflow integration.
6. Automated regression and deployed smoke tests.

PostgreSQL should be the source of truth for new AI Growth OS tenants. Google Sheets/Drive remains an optional compatibility integration during migration.