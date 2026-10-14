# AI Growth OS — Integration Gap Audit & Execution Plan

## Objective

Make AI Growth OS a single, integrated platform by reusing proven open-source components or hosted services only where they solve a verified gap. Do not replace working modules wholesale, introduce duplicate sources of truth, or change existing customer/tenant flows without a compatibility plan.

## Non-negotiable boundaries

- Preserve the existing Next.js + FastAPI + PostgreSQL + Redis deployment and current tenant identity model.
- Tenant data and platform-owner data must remain separate. Platform-owner marketing contacts/campaigns are external to AI Growth OS tenants.
- Platform-owner email and WhatsApp campaigns use only platform-owned sender credentials and platform-owned external contacts. Never select tenant contacts, tenant senders, or tenant inboxes in that workflow.
- Tenant/customer messaging remains in the tenant's own customer-engagement workflows.
- Existing AI customer WebRTC calls and booking workflows must not be replaced by a team-collaboration product.
- Integrations must be feature-flagged/configurable, tenant-scoped where appropriate, auditable, and removable without deleting core records.
- No credentials in source code; secrets remain in environment/configuration and encrypted credential storage.
- Verify licensing, active maintenance, security posture, data handling, deployment requirements, and migration/backup strategy before adopting any external codebase.
- No feature is declared complete until tests and the relevant deployment/health checks pass.

## Integration approach

1. Inventory the current routes, pages, models, permissions, migrations, and tests for each capability.
2. Mark each capability as working, incomplete, missing, or unverified based on code/tests—not assumptions.
3. Choose the smallest reusable unit: library, API adapter, embedded client, or separately deployed service.
4. Keep AI Growth OS as the system of record for tenant identity, roles, tenant/customer links, appointments, orders, and audit references.
5. Use adapters and stable internal IDs rather than copying an external product's database schema into the core.
6. Ship in small pull requests; add migration/backfill only when needed; preserve existing routes and UI.
7. Run regression tests and verify Render deployments before enabling a feature for production users.

## Capability map and candidate direction

| Capability | Current known foundation | Gap to verify | Integration direction |
|---|---|---|---|
| Super Admin / tenant onboarding | Existing FastAPI onboarding and tenant models | Tenant lifecycle, feature entitlements, permissions, auditability | Keep native; add capability registry and tests instead of importing another admin app |
| Customer PWA / QR | Existing customer PWA, QR entry and industry templates | Consistent one-scan routes and feature visibility by tenant | Keep native; add tests for persistent QR and tenant-specific routing |
| CRM / leads / customer identity | Existing Customer and Lead models, interactions | Deduplication, consent, timeline, imports/exports, follow-up tasks | Keep native system of record; adopt proven libraries for import/validation only if needed |
| Booking / queue / services / orders / payments | Existing appointment, queue, order, bill and payment-adapter foundations | End-to-end persistence, idempotency, status transitions and regression coverage | Keep native; test booking-to-CRM/order/call-record links before adding new dependencies |
| AI knowledge / routing | Existing knowledge library, FAQ, AI router and provider adapters | Grounding, multilingual quality, escalation, observability | Keep native router; provider adapters must remain replaceable |
| Customer voice calls | Existing WebRTC/voice gateway, call records and signaling | Real gateway connection, recovery, booking actions, call history, responsiveness timeout | Keep native customer-call runtime; never substitute a Slack-like team chat product |
| WhatsApp for tenants | Existing OpenWA/Meta adapter foundations | Webhook reliability, template lifecycle, delivery status, opt-out and provider fallback | Prefer official Meta WhatsApp Business Cloud API for production-compliant tenant messaging; retain OpenWA only where explicitly configured and risk-accepted |
| Platform-owner external marketing | Campaign-only Marketing Hub and platform sender helpers | Persistent external contact book, segments, consent/opt-out, campaign history, delivery reconciliation | Add a platform-owned contact/campaign data layer; evaluate listmonk as a separate email-marketing service only after auth, deployment, sync and license review. Do not expose tenant contacts/senders here |
| Email | Existing SMTP/Resend and email account models | Separate transactional notifications vs marketing subscriptions, bounce/unsubscribe handling | Keep transactional email native; marketing needs platform-only contacts and consent ledger; integrate rather than conflate |
| Internal team chat / voice / files | Existing team roles/permissions foundation; chat capability needs code audit | Channels, DMs, mentions, unread state, file sharing, team calls, audit and tenant boundaries | Evaluate Rocket.Chat first for Slack-like team collaboration and voice/video; Zulip is a lower-complexity text-first alternative. Do not install both. Require SSO/user lifecycle and tenant-isolation proof before selecting |
| Visitor management | Existing `routes_security.py`, `models_security.py`, `/dashboard/security`, QR token verification, human approval, check-in/out and append-only visitor events are present | Audit actual workflow gaps: filters/search, deny/cancel path, host notifications, site/gate handling, expiry/reporting, QR scan reliability, and feature/role access | Do not add a parallel visitor schema or duplicate routes. First strengthen the existing visitor module. Compare VisitorPass (FastAPI/Postgres/Redis/SQLAlchemy/Alembic) only for specific missing patterns after checking its license, maintenance and security; reuse selectively |
| Social publishing / analytics | Existing social routes and OAuth/provider integrations | Token refresh, provider permission errors, audit and retry behavior | Keep adapters; verify each provider's current API policy and test per capability |
| Monitoring / diagnostics / backups | Existing health, monitoring, self-heal and backup models | Alert delivery, actionable diagnostics, restore drills and per-tenant audit trails | Keep native foundations; integrate mature monitoring only when a verified operational gap exists |
| Loyalty / feedback / reviews | Existing loyalty, feedback and reward models | Append-only transactions, rule correctness, external review links and reporting | Keep native; protect balances with transaction and idempotency tests |
| Website generator / templates | Existing website template helpers | Safe preview/publish, versioning and tenant-specific overrides | Keep native unless an identified rendering/editor gap warrants a focused library |

## Candidate references (not yet adopted)

- VisitorPass: https://github.com/sadiq-codes/visitorpass — reported FastAPI, PostgreSQL, Redis, SQLAlchemy and Alembic stack, with QR visitor passes, check-in/out and admin workflows. Verify the actual LICENSE, maintenance, auth model, and code before reuse.
- Rocket.Chat: https://github.com/RocketChat/Rocket.Chat — candidate for internal channels, DMs, and team voice/video. Validate current license terms and deployment/SSO requirements for the selected edition.
- Zulip: https://github.com/zulip/zulip — Apache-2.0 text-first team collaboration alternative; do not run alongside Rocket.Chat unless a specific need justifies both.
- listmonk: https://github.com/knadh/listmonk — candidate for platform-owner external email lists/campaigns, subject to license and operational review. It is not a tenant CRM and must not receive tenant-owned marketing lists by default.
- Official WhatsApp Business Platform docs: https://developers.facebook.com/docs/whatsapp — preferred production API path where WhatsApp policy compliance and approved templates are required.

These are candidates, not approvals or claims that services have been deployed.

## Delivery sequence

### Phase A — Baseline and safety
- Inventory every current route/page/model/migration/test and produce a gap matrix.
- Verify latest GitHub and Render deployment state.
- Add regression checks for tenant isolation, permissions, external campaign recipient ownership, and existing booking/call flows.
- Record which modules are confirmed working vs merely present in code.

### Phase B — Highest-risk functional gaps
- Fix and prove booking persistence from voice/customer UI through the database and dashboard.
- Verify WebRTC gateway connection, call state recovery, call history and callback flow.
- Verify WhatsApp webhook ingress, sender configuration, delivery statuses, opt-outs and provider failure handling.
- Keep platform-owner campaigns isolated from all tenant data and add durable contact/campaign history.\n- Implemented in the current draft branch: a platform-only external contact table, authenticated list/import/archive endpoints, per-channel opt-in fields, duplicate-identity checks, opt-out ledger synchronization, and a Super Admin contact-book view.\n- Still required before campaign use: select saved contacts for a campaign, enforce per-channel contact opt-in in the send endpoint, persist campaign and per-recipient delivery history, and test opt-out/unsubscribe reconciliation end to end. This is a foundation, not a completed marketing CRM.

### Phase C — Team collaboration
- Audit current team UI, user/role lifecycle, file handling and notification patterns.
- Prototype one candidate behind a feature flag; test single sign-on or secure account provisioning, tenant boundaries, deactivation, audit logging and voice/video.
- Do not expose the service until tenant-isolation and identity lifecycle tests pass.

### Phase D — Visitor management
- Preserve the existing `routes_security.py`, `models_security.py`, and `/dashboard/security` implementation; do not create duplicate visitor tables or endpoints.
- Test the current create → pending → human approval → QR verification → check-in → check-out lifecycle and tenant isolation first.
- Improve the actual gaps in the existing page/API: search and status filters, clearer visit expiry and event history, deny/cancel handling, host/reception notifications, and useful operational reporting where required.
- Compare VisitorPass only against specific gaps and reuse selected patterns if license and code quality pass review.
- Add migrations only when a demonstrated gap requires new persisted fields; document rollback and test existing pass records before deployment.

### Phase E — Remaining capabilities
- Audit each row in the capability map, prioritize by user impact and failure risk, then implement in small isolated changes.
- Prefer adapters and libraries over importing entire products.
- Document deployment variables, provider setup, data ownership, failure modes and recovery for every integration.

## Definition of done

A feature is done only when:
- Code is integrated into the existing navigation and role/permission model.
- Data ownership and tenant isolation are tested.
- Migrations are backward compatible and backup/rollback steps are documented.
- Success, validation failure, provider failure, retry, duplicate submission and permission-denied cases are tested.
- Existing customer PWA, booking, CRM, voice, payments and tenant dashboard regression tests pass.
- Deployment is live and the relevant health check and real end-to-end smoke test pass.
