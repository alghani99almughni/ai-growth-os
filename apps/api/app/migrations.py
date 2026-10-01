from .db import Base,engine
from . import models,models_growth,models_ai,models_integrations
from sqlalchemy import text

def ensure_schema():
    Base.metadata.create_all(bind=engine)
    # Lightweight compatibility migration for deployments created before call handoff fields existed.
    with engine.begin() as conn:
        dialect=engine.dialect.name
        if dialect=="postgresql":
            conn.execute(text("CREATE TABLE IF NOT EXISTS ai_provider_usage (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36), provider VARCHAR(60) NOT NULL, model VARCHAR(120) NOT NULL, request_count INTEGER NOT NULL DEFAULT 0, success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0, rate_limit_count INTEGER NOT NULL DEFAULT 0, estimated_input_tokens INTEGER NOT NULL DEFAULT 0, estimated_output_tokens INTEGER NOT NULL DEFAULT 0, last_error TEXT, last_used_at TIMESTAMP, cooldown_until TIMESTAMP, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_provider_usage_tenant_provider ON ai_provider_usage(tenant_id, provider)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS idempotency_keys (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, scope VARCHAR(80) NOT NULL, key VARCHAR(200) NOT NULL, payload_hash VARCHAR(64) NOT NULL, response_json TEXT NOT NULL DEFAULT '{}', created_at TIMESTAMP NOT NULL, expires_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_idempotency_tenant_scope_key ON idempotency_keys(tenant_id, scope, key)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_idempotency_expires ON idempotency_keys(expires_at)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS audit_logs (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36), actor_id VARCHAR(36), action VARCHAR(80) NOT NULL, target_type VARCHAR(80) NOT NULL, target_id VARCHAR(120) NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}', request_id VARCHAR(64), created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_tenant_created ON audit_logs(tenant_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_target ON audit_logs(target_type, target_id)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_integrations (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, integration_key VARCHAR(60) NOT NULL, provider VARCHAR(60) NOT NULL, mode VARCHAR(20) NOT NULL DEFAULT 'platform', status VARCHAR(30) NOT NULL DEFAULT 'disconnected', config_encrypted TEXT NOT NULL DEFAULT '', account_name VARCHAR(200), account_id VARCHAR(200), metadata_json TEXT NOT NULL DEFAULT '{}', created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenant_integrations_tenant_id ON tenant_integrations(tenant_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_integrations_tenant_key ON tenant_integrations(tenant_id, integration_key)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS platform_ai_providers (id VARCHAR(36) PRIMARY KEY, provider VARCHAR(60) NOT NULL, model VARCHAR(120) NOT NULL, priority INTEGER NOT NULL DEFAULT 100, enabled BOOLEAN NOT NULL DEFAULT TRUE, config_encrypted TEXT NOT NULL DEFAULT '', status VARCHAR(30) NOT NULL DEFAULT 'healthy', last_error TEXT, last_used_at TIMESTAMP, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))

            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_whatsapp_connections (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL UNIQUE, provider VARCHAR(30) NOT NULL DEFAULT 'openwa', status VARCHAR(30) NOT NULL DEFAULT 'disconnected', config_encrypted TEXT NOT NULL DEFAULT '', connected_phone VARCHAR(32), display_name VARCHAR(160), created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'active'"))
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS agent_gender VARCHAR(10) DEFAULT 'female'"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS offline_calls (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, customer_name VARCHAR(160) DEFAULT 'Guest', customer_phone VARCHAR(32) DEFAULT '', customer_email VARCHAR(320), channel VARCHAR(30) DEFAULT 'widget_offline', language VARCHAR(16) DEFAULT 'en', call_started_at TIMESTAMP, audio_url TEXT, audio_size_bytes INTEGER DEFAULT 0, audio_duration_seconds INTEGER DEFAULT 0, transcript TEXT, reply TEXT, intent VARCHAR(120), language_detected VARCHAR(16), whatsapp_ok BOOLEAN DEFAULT FALSE, sms_ok BOOLEAN DEFAULT FALSE, email_ok BOOLEAN DEFAULT FALSE, lead_id VARCHAR(36), status VARCHAR(30) DEFAULT 'received', error TEXT, created_at TIMESTAMP NOT NULL, processed_at TIMESTAMP)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_offline_calls_tenant_status ON offline_calls(tenant_id, status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_offline_calls_status ON offline_calls(status)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS call_recordings (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, customer_id VARCHAR(36), call_record_id VARCHAR(36), customer_name VARCHAR(160) DEFAULT 'Guest', customer_phone VARCHAR(32) DEFAULT '', channel VARCHAR(30) DEFAULT 'webrtc', language_start VARCHAR(16) DEFAULT 'en', language_end VARCHAR(16) DEFAULT 'en', started_at TIMESTAMP, ended_at TIMESTAMP, duration_seconds INTEGER DEFAULT 0, turn_count INTEGER DEFAULT 0, status VARCHAR(30) DEFAULT 'in_progress', outcome VARCHAR(40), intent_final VARCHAR(120), has_flags BOOLEAN DEFAULT FALSE, flag_count INTEGER DEFAULT 0, severity VARCHAR(20), avg_turn_latency_ms INTEGER DEFAULT 0, total_customer_audio_bytes INTEGER DEFAULT 0, total_ai_audio_bytes INTEGER DEFAULT 0, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_call_recordings_tenant_started ON call_recordings(tenant_id, started_at)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS call_turns (id VARCHAR(36) PRIMARY KEY, recording_id VARCHAR(36) NOT NULL, turn_number INTEGER DEFAULT 1, ts_started TIMESTAMP, ts_ended TIMESTAMP, customer_text TEXT, customer_audio_url TEXT, customer_audio_ms INTEGER DEFAULT 0, stt_latency_ms INTEGER DEFAULT 0, intent VARCHAR(120), confidence FLOAT DEFAULT 0, language VARCHAR(16) DEFAULT 'en', entities_json TEXT DEFAULT '{}', source VARCHAR(30) DEFAULT 'handler', handler_name VARCHAR(80), handler_succeeded BOOLEAN DEFAULT FALSE, state_before VARCHAR(60), state_after VARCHAR(60), cleared_at_set BOOLEAN DEFAULT FALSE, ai_text TEXT, ai_audio_url TEXT, ai_audio_ms INTEGER DEFAULT 0, tts_latency_ms INTEGER DEFAULT 0, total_latency_ms INTEGER DEFAULT 0, tokens_used INTEGER DEFAULT 0, cost_usd FLOAT DEFAULT 0, error TEXT, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_call_turns_recording ON call_turns(recording_id, turn_number)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS call_flags (id VARCHAR(36) PRIMARY KEY, recording_id VARCHAR(36) NOT NULL, turn_id VARCHAR(36), flag_type VARCHAR(50) NOT NULL, severity VARCHAR(20) DEFAULT 'warning', message TEXT, details_json TEXT DEFAULT '{}', created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_call_flags_recording ON call_flags(recording_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_call_flags_type ON call_flags(flag_type)"))
            conn.execute(text("ALTER TABLE staff_members ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_staff_members_user_id ON staff_members(user_id) WHERE user_id IS NOT NULL"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS staff_id VARCHAR(36)"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS room_id VARCHAR(80)"))
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS email VARCHAR(320)"))
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS address TEXT"))
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS notes TEXT"))
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS tags TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS source VARCHAR(80) DEFAULT 'manual'"))
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS portal_token VARCHAR(100)"))
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS queue_enabled BOOLEAN DEFAULT TRUE"))
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS queue_threshold INTEGER DEFAULT 5"))
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS queue_avg_service_minutes INTEGER DEFAULT 15"))
            conn.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS staff_id VARCHAR(36)"))
            conn.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS ends_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS source VARCHAR(40) DEFAULT 'manual'"))
            conn.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS queue_token VARCHAR(40)"))
            conn.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS queue_status VARCHAR(40)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS service_requests (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, customer_id VARCHAR(36), appointment_id VARCHAR(36), context_token VARCHAR(100), request_type VARCHAR(50) NOT NULL DEFAULT 'waiter', message TEXT, status VARCHAR(40) NOT NULL DEFAULT 'requested', assigned_staff_id VARCHAR(36), created_at TIMESTAMP NOT NULL, acknowledged_at TIMESTAMP, completed_at TIMESTAMP)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS password_reset_tokens (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL, token_hash VARCHAR(128) NOT NULL UNIQUE, expires_at TIMESTAMP NOT NULL, used_at TIMESTAMP NULL, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS knowledge_candidates (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, language VARCHAR(16) NOT NULL DEFAULT 'en', intent VARCHAR(120), status VARCHAR(30) NOT NULL DEFAULT 'pending', source VARCHAR(40) NOT NULL DEFAULT 'voice', provider VARCHAR(60) NOT NULL DEFAULT 'ai', times_asked INTEGER NOT NULL DEFAULT 1, first_asked_at TIMESTAMP NOT NULL, last_asked_at TIMESTAMP NOT NULL, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_candidates_tenant_id ON knowledge_candidates(tenant_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_candidates_status ON knowledge_candidates(status)"))
            conn.execute(text("ALTER TABLE ai_provider_usage ADD COLUMN IF NOT EXISTS credential_ref VARCHAR(32) DEFAULT 'default'"))
            conn.execute(text("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS language VARCHAR(16) DEFAULT 'en'"))
            conn.execute(text("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS source VARCHAR(60) DEFAULT 'manual'"))
            conn.execute(text("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30) DEFAULT 'approved'"))
            conn.execute(text("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS usage_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS embedding_json TEXT"))
            conn.execute(text("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(80)"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS language VARCHAR(16) DEFAULT 'en'"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS started_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS answered_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS ended_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS duration_seconds INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS call_number INTEGER DEFAULT 1"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS resolution VARCHAR(50)"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS knowledge_hits INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS ai_turns INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE call_records ADD COLUMN IF NOT EXISTS human_callback_requested BOOLEAN DEFAULT FALSE"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_expires_at ON password_reset_tokens(expires_at)"))
        elif dialect=="sqlite":
            conn.execute(text("CREATE TABLE IF NOT EXISTS ai_provider_usage (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36), provider VARCHAR(60) NOT NULL, model VARCHAR(120) NOT NULL, request_count INTEGER NOT NULL DEFAULT 0, success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0, rate_limit_count INTEGER NOT NULL DEFAULT 0, estimated_input_tokens INTEGER NOT NULL DEFAULT 0, estimated_output_tokens INTEGER NOT NULL DEFAULT 0, last_error TEXT, last_used_at DATETIME, cooldown_until DATETIME, created_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_provider_usage_tenant_provider ON ai_provider_usage(tenant_id, provider)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS idempotency_keys (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, scope VARCHAR(80) NOT NULL, key VARCHAR(200) NOT NULL, payload_hash VARCHAR(64) NOT NULL, response_json TEXT NOT NULL DEFAULT '{}', created_at DATETIME NOT NULL, expires_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_idempotency_tenant_scope_key ON idempotency_keys(tenant_id, scope, key)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_idempotency_expires ON idempotency_keys(expires_at)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS audit_logs (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36), actor_id VARCHAR(36), action VARCHAR(80) NOT NULL, target_type VARCHAR(80) NOT NULL, target_id VARCHAR(120) NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}', request_id VARCHAR(64), created_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_tenant_created ON audit_logs(tenant_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_target ON audit_logs(target_type, target_id)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_integrations (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, integration_key VARCHAR(60) NOT NULL, provider VARCHAR(60) NOT NULL, mode VARCHAR(20) NOT NULL DEFAULT 'platform', status VARCHAR(30) NOT NULL DEFAULT 'disconnected', config_encrypted TEXT NOT NULL DEFAULT '', account_name VARCHAR(200), account_id VARCHAR(200), metadata_json TEXT NOT NULL DEFAULT '{}', created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenant_integrations_tenant_id ON tenant_integrations(tenant_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_integrations_tenant_key ON tenant_integrations(tenant_id, integration_key)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS platform_ai_providers (id VARCHAR(36) PRIMARY KEY, provider VARCHAR(60) NOT NULL, model VARCHAR(120) NOT NULL, priority INTEGER NOT NULL DEFAULT 100, enabled BOOLEAN NOT NULL DEFAULT 1, config_encrypted TEXT NOT NULL DEFAULT '', status VARCHAR(30) NOT NULL DEFAULT 'healthy', last_error TEXT, last_used_at DATETIME, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))

            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_whatsapp_connections (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL UNIQUE, provider VARCHAR(30) NOT NULL DEFAULT 'openwa', status VARCHAR(30) NOT NULL DEFAULT 'disconnected', config_encrypted TEXT NOT NULL DEFAULT '', connected_phone VARCHAR(32), display_name VARCHAR(160), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS password_reset_tokens (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL, token_hash VARCHAR(128) NOT NULL UNIQUE, expires_at DATETIME NOT NULL, used_at DATETIME NULL, created_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_expires_at ON password_reset_tokens(expires_at)"))
            tenant_cols={r[1] for r in conn.execute(text("PRAGMA table_info(tenants)"))}
            if "status" not in tenant_cols: conn.execute(text("ALTER TABLE tenants ADD COLUMN status VARCHAR(30) DEFAULT 'active'"))
            staff_cols={r[1] for r in conn.execute(text("PRAGMA table_info(staff_members)"))}
            if "user_id" not in staff_cols: conn.execute(text("ALTER TABLE staff_members ADD COLUMN user_id VARCHAR(36)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_staff_members_user_id ON staff_members(user_id)"))
            cols={r[1] for r in conn.execute(text("PRAGMA table_info(call_records)"))}
            if "staff_id" not in cols: conn.execute(text("ALTER TABLE call_records ADD COLUMN staff_id VARCHAR(36)"))
            if "room_id" not in cols: conn.execute(text("ALTER TABLE call_records ADD COLUMN room_id VARCHAR(80)"))
            customer_cols={r[1] for r in conn.execute(text("PRAGMA table_info(customers)"))}
            if "email" not in customer_cols: conn.execute(text("ALTER TABLE customers ADD COLUMN email VARCHAR(320)"))
            if "address" not in customer_cols: conn.execute(text("ALTER TABLE customers ADD COLUMN address TEXT"))
            if "notes" not in customer_cols: conn.execute(text("ALTER TABLE customers ADD COLUMN notes TEXT"))
            if "tags" not in customer_cols: conn.execute(text("ALTER TABLE customers ADD COLUMN tags VARCHAR(500) DEFAULT ''"))
            if "source" not in customer_cols: conn.execute(text("ALTER TABLE customers ADD COLUMN source VARCHAR(80) DEFAULT 'manual'"))
            if "portal_token" not in customer_cols: conn.execute(text("ALTER TABLE customers ADD COLUMN portal_token VARCHAR(100)"))
            tenant_cols={r[1] for r in conn.execute(text("PRAGMA table_info(tenants)"))}
            if "queue_enabled" not in tenant_cols: conn.execute(text("ALTER TABLE tenants ADD COLUMN queue_enabled BOOLEAN DEFAULT 1"))
            if "queue_threshold" not in tenant_cols: conn.execute(text("ALTER TABLE tenants ADD COLUMN queue_threshold INTEGER DEFAULT 5"))
            if "queue_avg_service_minutes" not in tenant_cols: conn.execute(text("ALTER TABLE tenants ADD COLUMN queue_avg_service_minutes INTEGER DEFAULT 15"))
            appointment_cols={r[1] for r in conn.execute(text("PRAGMA table_info(appointments)"))}
            if "staff_id" not in appointment_cols: conn.execute(text("ALTER TABLE appointments ADD COLUMN staff_id VARCHAR(36)"))
            if "ends_at" not in appointment_cols: conn.execute(text("ALTER TABLE appointments ADD COLUMN ends_at DATETIME"))
            if "source" not in appointment_cols: conn.execute(text("ALTER TABLE appointments ADD COLUMN source VARCHAR(40) DEFAULT 'manual'"))
            if "queue_token" not in appointment_cols: conn.execute(text("ALTER TABLE appointments ADD COLUMN queue_token VARCHAR(40)"))
            if "queue_status" not in appointment_cols: conn.execute(text("ALTER TABLE appointments ADD COLUMN queue_status VARCHAR(40)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS knowledge_candidates (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, language VARCHAR(16) NOT NULL DEFAULT 'en', intent VARCHAR(120), status VARCHAR(30) NOT NULL DEFAULT 'pending', source VARCHAR(40) NOT NULL DEFAULT 'voice', provider VARCHAR(60) NOT NULL DEFAULT 'ai', times_asked INTEGER NOT NULL DEFAULT 1, first_asked_at DATETIME NOT NULL, last_asked_at DATETIME NOT NULL, created_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_candidates_tenant_id ON knowledge_candidates(tenant_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_candidates_status ON knowledge_candidates(status)"))
            ai_usage_cols={r[1] for r in conn.execute(text("PRAGMA table_info(ai_provider_usage)"))}
            if "credential_ref" not in ai_usage_cols: conn.execute(text("ALTER TABLE ai_provider_usage ADD COLUMN credential_ref VARCHAR(32) DEFAULT 'default'"))
            knowledge_cols={r[1] for r in conn.execute(text("PRAGMA table_info(knowledge_items)"))}
            for name,definition in [("language","VARCHAR(16) DEFAULT 'en'"),("source","VARCHAR(60) DEFAULT 'manual'"),("approval_status","VARCHAR(30) DEFAULT 'approved'"),("usage_count","INTEGER DEFAULT 0"),("last_used_at","DATETIME"),("embedding_json","TEXT"),("embedding_model","VARCHAR(80)")]:
                if name not in knowledge_cols: conn.execute(text(f"ALTER TABLE knowledge_items ADD COLUMN {name} {definition}"))
            call_cols={r[1] for r in conn.execute(text("PRAGMA table_info(call_records)"))}
            for name,definition in [("language","VARCHAR(16) DEFAULT 'en'"),("started_at","DATETIME"),("answered_at","DATETIME"),("ended_at","DATETIME"),("duration_seconds","INTEGER DEFAULT 0"),("call_number","INTEGER DEFAULT 1"),("resolution","VARCHAR(50)"),("knowledge_hits","INTEGER DEFAULT 0"),("ai_turns","INTEGER DEFAULT 0"),("human_callback_requested","BOOLEAN DEFAULT 0")]:
                if name not in call_cols: conn.execute(text(f"ALTER TABLE call_records ADD COLUMN {name} {definition}"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS service_requests (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, customer_id VARCHAR(36), appointment_id VARCHAR(36), context_token VARCHAR(100), request_type VARCHAR(50) NOT NULL DEFAULT 'waiter', message TEXT, status VARCHAR(40) NOT NULL DEFAULT 'requested', assigned_staff_id VARCHAR(36), created_at DATETIME NOT NULL, acknowledged_at DATETIME, completed_at DATETIME)"))
def ensure_email_schema() -> None:
    """Create email-specific tables if they don't exist yet."""
    from .db import engine, Base
    from . import models_email  # noqa: F401  (import registers tables on Base.metadata)
    Base.metadata.create_all(bind=engine, tables=[
        models_email.TenantEmailAccount.__table__,
        models_email.EmailLog.__table__,
    ])


def ensure_monitoring_schema() -> None:
    """Create monitoring-specific tables if they don't exist yet."""
    from .db import engine, Base
    from . import models_monitoring  # noqa: F401
    Base.metadata.create_all(bind=engine, tables=[
        models_monitoring.HealthSnapshot.__table__,
        models_monitoring.SelfHealAction.__table__,
        models_monitoring.MonitoringAlert.__table__,
        models_monitoring.BackupRecord.__table__,
    ])


def ensure_monitoring_schema() -> None:
    """Create monitoring-specific tables if they don't exist yet."""
    from .db import engine, Base
    from . import models_monitoring  # noqa: F401
    Base.metadata.create_all(bind=engine, tables=[
        models_monitoring.HealthSnapshot.__table__,
        models_monitoring.SelfHealAction.__table__,
        models_monitoring.MonitoringAlert.__table__,
        models_monitoring.BackupRecord.__table__,
    ])