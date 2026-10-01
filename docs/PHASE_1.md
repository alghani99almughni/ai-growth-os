# Phase 1 implementation contract

Phase 1 establishes the first deployable foundation for AI Growth OS.

## Included
- Next.js-ready web application shell
- FastAPI backend
- PostgreSQL and Redis development services
- Multi-tenant tenant/customer/lead model foundation
- Industry template contract
- Safe AI chat endpoint placeholder
- PWA manifest and dashboard shell

## Multi-tenancy
Every business-owned record must carry `tenant_id`. Future APIs must derive tenant identity from authenticated context and enforce ownership server-side; never trust a client-supplied tenant ID.

## AI safety
AI must answer from approved business knowledge and controlled backend tools. It must not invent prices, availability, policies, discounts, booking/payment success, or clinical advice.

## Next implementation slice
Authentication, migrations, tenant onboarding, tenant-scoped CRUD, customer identity, real AI adapter, lead creation, generated customer PWA, tests, CI, and deployment manifests.
