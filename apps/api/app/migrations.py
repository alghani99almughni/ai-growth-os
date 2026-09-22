from .db import Base,engine
from . import models,models_growth,models_ai,models_integrations
from sqlalchemy import text

def ensure_schema():
    Base.metadata.create_all(bind=engine)
    # Lightweight compatibility migration for deployments created before call handoff fields existed.
    with engine.begin() as conn:
        dialect=engine.dialect.name
        if dialect=="postgresql":
            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_integrations (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, integration_key VARCHAR(60) NOT NULL, provider VARCHAR(60) NOT NULL, mode VARCHAR(20) NOT NULL DEFAULT 'platform', status VARCHAR(30) NOT NULL DEFAULT 'disconnected', config_encrypted TEXT NOT NULL DEFAULT '', account_name VARCHAR(200), account_id VARCHAR(200), metadata_json TEXT NOT NULL DEFAULT '{}', created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenant_integrations_tenant_id ON tenant_integrations(tenant_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_integrations_tenant_key ON tenant_integrations(tenant_id, integration_key)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS platform_ai_providers (id VARCHAR(36) PRIMARY KEY, provider VARCHAR(60) NOT NULL, model VARCHAR(120) NOT NULL, priority INTEGER NOT NULL DEFAULT 100, enabled BOOLEAN NOT NULL DEFAULT TRUE, config_encrypted TEXT NOT NULL DEFAULT '', status VARCHAR(30) NOT NULL DEFAULT 'healthy', last_error TEXT, last_used_at TIMESTAMP, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))

            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_whatsapp_connections (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL UNIQUE, provider VARCHAR(30) NOT NULL DEFAULT 'openwa', status VARCHAR(30) NOT NULL DEFAULT 'disconnected', config_encrypted TEXT NOT NULL DEFAULT '', connected_phone VARCHAR(32), display_name VARCHAR(160), created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'active'"))
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
        elif dialect=="sqlite":
            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_integrations (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, integration_key VARCHAR(60) NOT NULL, provider VARCHAR(60) NOT NULL, mode VARCHAR(20) NOT NULL DEFAULT 'platform', status VARCHAR(30) NOT NULL DEFAULT 'disconnected', config_encrypted TEXT NOT NULL DEFAULT '', account_name VARCHAR(200), account_id VARCHAR(200), metadata_json TEXT NOT NULL DEFAULT '{}', created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenant_integrations_tenant_id ON tenant_integrations(tenant_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_integrations_tenant_key ON tenant_integrations(tenant_id, integration_key)"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS platform_ai_providers (id VARCHAR(36) PRIMARY KEY, provider VARCHAR(60) NOT NULL, model VARCHAR(120) NOT NULL, priority INTEGER NOT NULL DEFAULT 100, enabled BOOLEAN NOT NULL DEFAULT 1, config_encrypted TEXT NOT NULL DEFAULT '', status VARCHAR(30) NOT NULL DEFAULT 'healthy', last_error TEXT, last_used_at DATETIME, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))

            conn.execute(text("CREATE TABLE IF NOT EXISTS tenant_whatsapp_connections (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL UNIQUE, provider VARCHAR(30) NOT NULL DEFAULT 'openwa', status VARCHAR(30) NOT NULL DEFAULT 'disconnected', config_encrypted TEXT NOT NULL DEFAULT '', connected_phone VARCHAR(32), display_name VARCHAR(160), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))
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
            conn.execute(text("CREATE TABLE IF NOT EXISTS service_requests (id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, customer_id VARCHAR(36), appointment_id VARCHAR(36), context_token VARCHAR(100), request_type VARCHAR(50) NOT NULL DEFAULT 'waiter', message TEXT, status VARCHAR(40) NOT NULL DEFAULT 'requested', assigned_staff_id VARCHAR(36), created_at DATETIME NOT NULL, acknowledged_at DATETIME, completed_at DATETIME)"))
