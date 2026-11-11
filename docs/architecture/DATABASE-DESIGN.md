# AEO/GEO Visibility Module — Data Design

## Design rules
- Use a dedicated PostgreSQL database and isolated SQLAlchemy metadata/session for visibility data; do not add visibility tables to the existing AI Growth OS operational database.
- Use existing tenant/user/plan models where suitable.
- All tenant-owned tables carry `tenant_id`, timestamps, and appropriate indexes.
- IDs should follow repository conventions (UUID/string IDs if that is the established pattern).
- Store normalized evidence separately from optional bounded raw provider payloads. Never store credentials in result records.

## Database isolation boundary

- The platform database remains authoritative for authentication, users, tenants, subscriptions, and integration credentials.
- A separate `VISIBILITY_DATABASE_URL` points to the dedicated `ai-growth-os-visibility-db` Postgres resource.
- Visibility tables are registered only on `VisibilityBase.metadata` and are initialized independently.
- Visibility records store the platform's `tenant_id` as an opaque string. They must not declare cross-database foreign keys to `tenants.id`.
- Relationships among visibility-owned records (for example, check run to query, observation to run, and finding to audit) remain local foreign keys inside the visibility database.
- API authentication and tenant authorization continue to use the existing platform database. Visibility CRUD uses the isolated visibility session. Google OAuth credentials are read from the platform integration store and are never copied into visibility records.
- This separation keeps the current operational schema unchanged and leaves a controlled future data-consolidation path.

## Proposed entities

### VisibilityBrand
- `id`
- `tenant_id` (required, indexed)
- `name`
- `primary_domain`
- `business_description` (bounded)
- `service_areas` (structured JSON if supported by project conventions)
- `locale`
- `created_at`, `updated_at`

One primary profile per tenant can be enforced in service logic initially; add a database uniqueness constraint only after confirming supported migration patterns.

### VisibilityCompetitor
- `id`
- `tenant_id` (required, indexed)
- `name`
- `domain`
- `notes` (optional, bounded)
- `created_at`, `updated_at`

### VisibilityQuery
- `id`
- `tenant_id` (required, indexed)
- `query_text` (bounded)
- `intent` (informational, local, comparison, transactional, or other)
- `locale`
- `topic`
- `is_active`
- `created_at`, `updated_at`

### VisibilityAudit
- `id`
- `tenant_id` (required, indexed)
- `brand_id`
- `target_url`
- `status` (queued, running, completed, partial, failed)
- `started_at`, `completed_at`
- `pages_checked`
- `summary_json` (bounded structured summary)
- `error_code` (safe, non-secret)
- `created_at`

### VisibilityAuditFinding
- `id`
- `tenant_id` (required, indexed)
- `audit_id` (required, indexed)
- `page_url`
- `category`
- `severity`
- `finding_code`
- `title`
- `description`
- `recommendation`
- `evidence_json` (bounded)
- `created_at`

### VisibilityCheckRun
- `id`
- `tenant_id` (required, indexed)
- `query_id`
- `provider`
- `measurement_method` (search_grounded, model_sampled, or other explicit method)
- `status` (queued, running, completed, partial, failed)
- `started_at`, `completed_at`
- `request_fingerprint` (for safe idempotency/deduplication)
- `error_code`
- `created_at`

### VisibilityObservation
- `id`
- `tenant_id` (required, indexed)
- `run_id` (required, indexed)
- `brand_mentioned`
- `mentioned_names_json`
- `answer_excerpt` (bounded and privacy-reviewed)
- `cited_urls_json`
- `position_or_rank` (nullable; only when provider explicitly supplies a meaningful value)
- `evidence_quality`
- `observed_at`

### VisibilityUsageEvent
- `id`
- `tenant_id` (required, indexed)
- `event_type`
- `units`
- `provider`
- `run_id` (nullable)
- `created_at`

## Constraints and indexes
- Index tenant and creation time for history screens.
- Index `tenant_id + status` for queued/running jobs.
- Index `tenant_id + query_id + created_at` for trend lookups.
- Unique/idempotency constraint on a stable run fingerprint where compatible with existing schema conventions.
- Foreign keys must prevent child records from being attached to unrelated tenant-owned parents; validate tenant ownership in service code as well.

## Retention and privacy
Set explicit retention for raw provider payloads and answer excerpts. Keep only what is necessary to explain a measurement. Never persist API keys, cookies, authorization headers, or private page content. Retention periods must be configurable and documented before production launch.

## Migration gate
No migration should run against production until it has been reviewed, exercised against a disposable/test database, and a backup/rollback plan has been verified.
