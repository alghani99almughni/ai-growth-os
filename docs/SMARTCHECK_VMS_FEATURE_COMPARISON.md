# Visitor Management Comparison and AI Growth OS Adaptation

## Decision

Extend the existing AI Growth OS Security & Visitor Management module and preserve the SmartCheck Google Sheets / Apps Script workflow as the initial system of record. Do not import another repository's application wholesale and do not create a parallel visitor database before the planned migration.

Reference: the supplied `SmartCheck_Hardened_Apps_Script.gs` defines `MultipleTenantRegister`, `AuthorizedUsers`, and `GatePassLogs`; it supports authenticated `VISITOR_REQUEST`, `LIST_VISITORS`, `APPROVE_VISITOR`, `REJECT_VISITOR`, `CHECK_IN`, and `CHECK_OUT`. Its current action list does not include QR-token verification. Existing legacy tenant codes (for example, `TNT-101`) must be mapped to AI Growth OS tenant UUIDs, never assumed to be the same identifier.

## Public GitHub patterns reviewed

| Reference | Useful pattern | Adoption decision |
|---|---|---|
| [GitHub visitor-management-system topic](https://github.com/topics/visitor-management-system) | Broad feature discovery: QR passes, approvals, guard workflow, audit history | Use as a feature checklist, not as source code |
| [wangjiongwei8/visitor-management](https://github.com/wangjiongwei8/visitor-management) | Visitor self-registration by fixed QR, host pre-registration/review, guard check-in and auditable access lifecycle; project states MIT license | Adopt the workflow ideas. Do not copy code without reviewing the repository and dependencies at the exact version |
| [BensOmnitrix/vms](https://github.com/BensOmnitrix/vms) | Role-based Visitor/Host/Guard/Admin views, QR check-in/out, notifications, blacklist, multi-day passes and PWA | Adopt the feature concepts where compatible; license compatibility must be independently verified before copying code |
| [Rajeev02/Visitor-Management-System](https://github.com/Rajeev02/Visitor-Management-System) | QR pass lifecycle, role-based dashboard, audit workflow | Use as a cross-check for role and gate workflow; do not port its React Native/Firebase stack |
| [AdityaJanjire/visitor-management-system-](https://github.com/AdityaJanjire/visitor-management-system-) | QR visitor passes, photo/ID capture, trusted entities and blacklist concepts | Candidate future features only; do not introduce Supabase as a competing source of truth |

This is a design/feature comparison, not a claim that each repository's current code, dependencies, license, or security posture has been fully audited. No third-party source code is copied by this document.

## What AI Growth OS already has

- Tenant-scoped API with a server-side opt-in feature flag.
- Tenant sites with School, Apartment, and Hospital industry values.
- Visitor request/pass creation, mandatory human approval, denial and cancellation.
- QR token generation/rendering and authenticated camera/token verification.
- Separate authorized check-in and check-out actions.
- Visitor event/audit records.
- Tenant dashboard search, status filtering, pending/approved/inside/closed counts.
- SmartCheck connection settings UI (draft PR #52), but only URL reachability is currently checked.

## What should be added, in order

### P0 — Complete SmartCheck compatibility before calling the integration live

1. Keep the existing Apps Script/Sheets records authoritative during the compatibility period.
2. Store the bridge secret server-side only; never send it to the browser or put it in URLs/QR codes.
3. Implemented in this branch: the Super Admin connection form stores a per-tenant legacy SmartCheck code mapping, validates allowed characters, and rejects a code already mapped to a different AI Growth OS tenant. The mapping is configuration only until authenticated bridge calls are implemented; it does not create or change SmartCheck tenant rows.
4. Implement server-side authenticated `PING` and integration calls with timeouts, bounded responses, strict HTTPS host validation, and clear error states.
5. Add bridge actions/contract for QR verification or use a signed opaque AI Growth OS token mapped to the SmartCheck ticket ID. Until one is implemented and tested, do not claim SmartCheck QR verification is integrated.
6. Keep the current local API/dashboard contracts stable while the adapter is introduced. No automatic fallback that writes to a second database after a bridge failure.

### P1 — Visitor-friendly QR entry

- Fixed tenant/site QR opens a mobile web form without requiring PWA installation.
- Collect only the fields required by that tenant's policy; default to visitor name and mobile, plus purpose, host/destination, and optional vehicle number where enabled.
- Submit as **Pending**; never grant entry from public registration or an AI/chat/voice request.
- Offer PWA installation only as an optional convenience for repeat visitors.
- Provide a reference/ticket and a status-check path that does not disclose another visitor's personal details.
- Apply server-side rate limits, input limits, duplicate-submission protection, expiry, and tenant/site scoping.

### P2 — Security operations

- Host/department pre-registration and approval inbox with recorded approver identity.
- Optional tenant-scoped watchlist/blocked visitor records with reason, expiry, strict access controls, and audit trail. Do not implement face recognition or silently infer identity.
- Time-bounded passes with explicit valid-from/valid-until checks, including multi-day passes only when tenant policy allows them.
- Guard/gate role permissions, gate/site scoping, and an explicit “already inside”/“already used” state.
- Optional photo or ID-document capture only where enabled by tenant policy, with retention limits and restricted access.
- Exportable daily visitor register and “currently inside” report; preserve audit events.
- Optional notifications through configured tenant channels; notifications must not be the source of truth for approval.

### P3 — Resilience and convenience

- Optional PWA install prompt for repeat visitors.
- Accessible camera scanner with manual token fallback (already present in the tenant dashboard).
- Offline gate mode only after designing signed, short-lived passes and replay protection; do not allow offline mode to bypass approval.
- Printable badge/PDF and visitor analytics after the bridge and event lifecycle are reliable.

## Non-negotiable security and data rules

- Feature remains disabled unless enabled for that tenant by platform/tenant configuration.
- Never trust a tenant ID, tenant code, role, approval state, or status supplied by the public browser.
- AI/chat/voice can request a visit but cannot approve it or check a visitor in.
- Tenant isolation must apply to reads, writes, QR verification, exports, and watchlists.
- Audit approval, denial, check-in, check-out, expiry, cancellation, and privileged configuration changes.
- A Drive folder sharing URL is not an OAuth grant. A successful Apps Script `HEALTH` request is not authenticated bridge sync.
- No production “Connected” status until authenticated `PING`, tenant mapping, a real read/write round-trip, and failure tests pass.
- No merge or deployment without test evidence and explicit release approval.

## Acceptance gates

1. Unit tests for tenant mapping, bridge authentication, timeouts, invalid responses, and role enforcement.
2. Integration tests for request → approve/reject → check-in → check-out, including invalid state transitions and expired tokens.
3. Cross-tenant tests for every endpoint and public QR entry.
4. Existing Apps Script rows remain readable and unchanged except for explicitly requested operations.
5. School, Apartment, and Hospital flows verified against the same shared engine and tenant-specific policy.
6. API tests and frontend build pass; PR reviewed before release.
