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

            # ── New columns added in later sessions ──
            conn.execute(text("ALTER TABLE platform_settings ADD COLUMN IF NOT EXISTS updated_by VARCHAR(36)"))
            conn.execute(text("ALTER TABLE platform_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))

            # ── Tables added in later sessions (Session 17b, 18, 20a) ──
            conn.execute(text("CREATE TABLE IF NOT EXISTS support_tickets (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, subject VARCHAR(300) NOT NULL, body TEXT, category VARCHAR(40) NOT NULL DEFAULT 'support', priority VARCHAR(20) NOT NULL DEFAULT 'normal', status VARCHAR(40) NOT NULL DEFAULT 'new', sla_hours INTEGER NOT NULL DEFAULT 24, sla_due_at TIMESTAMP, sla_breached BOOLEAN NOT NULL DEFAULT FALSE, assigned_to VARCHAR(36), created_by VARCHAR(36), created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL, resolved_at TIMESTAMP, resolved_by VARCHAR(36))"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_tenant_id ON support_tickets(tenant_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets(status)"))

            conn.execute(text("CREATE TABLE IF NOT EXISTS platform_messages (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, subject VARCHAR(300) NOT NULL, body TEXT, from_admin_id VARCHAR(36), read_at TIMESTAMP, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_messages_tenant_id ON platform_messages(tenant_id)"))

            conn.execute(text("CREATE TABLE IF NOT EXISTS platform_tasks (id VARCHAR(36) PRIMARY KEY, title VARCHAR(300) NOT NULL, notes TEXT DEFAULT '', due_at TIMESTAMP NOT NULL, duration_minutes INTEGER NOT NULL DEFAULT 30, all_day BOOLEAN NOT NULL DEFAULT FALSE, tenant_id VARCHAR(36), kind VARCHAR(40) NOT NULL DEFAULT 'followup', priority VARCHAR(20) NOT NULL DEFAULT 'normal', status VARCHAR(30) NOT NULL DEFAULT 'pending', created_by VARCHAR(36), created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_tasks_due_at ON platform_tasks(due_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_tasks_tenant_id ON platform_tasks(tenant_id)"))

            # ── Email integration (Session 18) ──
            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_email_accounts (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, label VARCHAR(120) NOT NULL DEFAULT 'Primary mailbox', provider VARCHAR(30) NOT NULL DEFAULT 'custom', email_address VARCHAR(200) NOT NULL, config_encrypted TEXT NOT NULL, role VARCHAR(30) NOT NULL DEFAULT 'general', is_active BOOLEAN NOT NULL DEFAULT TRUE, auto_reply_enabled BOOLEAN NOT NULL DEFAULT TRUE, last_checked_at TIMESTAMP, last_error TEXT, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenant_email_accounts_tenant_id ON tenant_email_accounts(tenant_id)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS email_logs (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, account_id VARCHAR(36) NOT NULL, message_id VARCHAR(500) NOT NULL, from_address VARCHAR(320) NOT NULL, to_address VARCHAR(320) NOT NULL, subject VARCHAR(500) NOT NULL DEFAULT '', outcome VARCHAR(30) NOT NULL DEFAULT 'replied', reply_text TEXT, error TEXT, ticket_id VARCHAR(36), created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_email_logs_tenant_id ON email_logs(tenant_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_email_logs_message_id ON email_logs(message_id)"))

            # ── Monitoring (Session 20a) ──
            conn.execute(text("CREATE TABLE IF NOT EXISTS monitoring_health_snapshots (id VARCHAR(36) PRIMARY KEY, category VARCHAR(40) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'unknown', detail_json TEXT NOT NULL DEFAULT '{}', latency_ms INTEGER, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_monitoring_health_snapshots_category ON monitoring_health_snapshots(category)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS monitoring_self_heal_actions (id VARCHAR(36) PRIMARY KEY, component VARCHAR(60) NOT NULL, action VARCHAR(120) NOT NULL, outcome VARCHAR(20) NOT NULL DEFAULT 'skipped', detail TEXT, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_monitoring_self_heal_actions_component ON monitoring_self_heal_actions(component)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS monitoring_alerts (id VARCHAR(36) PRIMARY KEY, severity VARCHAR(20) NOT NULL DEFAULT 'warning', component VARCHAR(60) NOT NULL, title VARCHAR(300) NOT NULL, body TEXT NOT NULL DEFAULT '', email_sent BOOLEAN NOT NULL DEFAULT FALSE, whatsapp_sent BOOLEAN NOT NULL DEFAULT FALSE, delivery_error TEXT, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_monitoring_alerts_created_at ON monitoring_alerts(created_at)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS monitoring_backups (id VARCHAR(36) PRIMARY KEY, source_path VARCHAR(500) NOT NULL, backup_path VARCHAR(500) NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0, ok BOOLEAN NOT NULL DEFAULT TRUE, error TEXT, created_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_monitoring_backups_created_at ON monitoring_backups(created_at)"))


def ensure_email_schema() -> None:
    """Create email-specific tables if they don't exist yet."""
    from .db import engine as _engine, Base as _Base
    from . import models_email  # noqa: F401
    _Base.metadata.create_all(bind=_engine, tables=[
        models_email.TenantEmailAccount.__table__,
        models_email.EmailLog.__table__,
    ])


def ensure_monitoring_schema() -> None:
    """Create monitoring-specific tables if they don't exist yet."""
    from .db import engine as _engine, Base as _Base
    from . import models_monitoring  # noqa: F401
    _Base.metadata.create_all(bind=_engine, tables=[
        models_monitoring.HealthSnapshot.__table__,
        models_monitoring.SelfHealAction.__table__,
        models_monitoring.MonitoringAlert.__table__,
        models_monitoring.BackupRecord.__table__,
    ])