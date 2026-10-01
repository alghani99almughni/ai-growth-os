"""Session 17a - migration.

Adds:
    - platform_settings table
    - support_tickets table
    - platform_messages table
    - tenants.last_seen_at, health_status, region, compliance_flags, created_by_admin_id
"""
import logging
import pathlib
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("migration17a")

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    from sqlalchemy import text
    from app.db import engine
except Exception as exc:
    print("ERROR: could not import app.db:", exc)
    print("Make sure you run this from apps/api.")
    sys.exit(1)

DIALECT = engine.dialect.name
print(f"Dialect: {DIALECT}")


def run_postgres(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS platform_settings (
            id VARCHAR(36) PRIMARY KEY,
            key VARCHAR(120) NOT NULL UNIQUE,
            value_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP NOT NULL,
            updated_by VARCHAR(36)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_settings_key ON platform_settings(key)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(36) NOT NULL,
            subject VARCHAR(300) NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            category VARCHAR(60) NOT NULL DEFAULT 'support',
            priority VARCHAR(20) NOT NULL DEFAULT 'normal',
            status VARCHAR(40) NOT NULL DEFAULT 'new',
            sla_hours INTEGER NOT NULL DEFAULT 24,
            sla_due_at TIMESTAMP,
            sla_breached BOOLEAN NOT NULL DEFAULT FALSE,
            assigned_to VARCHAR(36),
            created_by VARCHAR(36),
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            resolved_at TIMESTAMP,
            resolved_by VARCHAR(36)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_tenant ON support_tickets(tenant_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets(status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_sla_due ON support_tickets(sla_due_at)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS platform_messages (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(36) NOT NULL,
            subject VARCHAR(300) NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            from_admin_id VARCHAR(36),
            read_at TIMESTAMP,
            email_sent BOOLEAN NOT NULL DEFAULT FALSE,
            email_status VARCHAR(40),
            created_at TIMESTAMP NOT NULL
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_messages_tenant ON platform_messages(tenant_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_messages_created ON platform_messages(created_at)"))

    conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP"))
    conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS health_status VARCHAR(20) DEFAULT 'unknown'"))
    conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS region VARCHAR(20) DEFAULT 'GLOBAL'"))
    conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS compliance_flags TEXT DEFAULT '{}'"))
    conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS created_by_admin_id VARCHAR(36)"))


def run_sqlite(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS platform_settings (
            id VARCHAR(36) PRIMARY KEY,
            key VARCHAR(120) NOT NULL UNIQUE,
            value_json TEXT NOT NULL DEFAULT '{}',
            updated_at DATETIME NOT NULL,
            updated_by VARCHAR(36)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_settings_key ON platform_settings(key)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(36) NOT NULL,
            subject VARCHAR(300) NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            category VARCHAR(60) NOT NULL DEFAULT 'support',
            priority VARCHAR(20) NOT NULL DEFAULT 'normal',
            status VARCHAR(40) NOT NULL DEFAULT 'new',
            sla_hours INTEGER NOT NULL DEFAULT 24,
            sla_due_at DATETIME,
            sla_breached BOOLEAN NOT NULL DEFAULT 0,
            assigned_to VARCHAR(36),
            created_by VARCHAR(36),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            resolved_at DATETIME,
            resolved_by VARCHAR(36)
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_tenant ON support_tickets(tenant_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets(status)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS platform_messages (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(36) NOT NULL,
            subject VARCHAR(300) NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            from_admin_id VARCHAR(36),
            read_at DATETIME,
            email_sent BOOLEAN NOT NULL DEFAULT 0,
            email_status VARCHAR(40),
            created_at DATETIME NOT NULL
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_messages_tenant ON platform_messages(tenant_id)"))

    cols = {r[1] for r in conn.execute(text("PRAGMA table_info(tenants)"))}
    additions = [
        ("last_seen_at", "DATETIME"),
        ("health_status", "VARCHAR(20) DEFAULT 'unknown'"),
        ("region", "VARCHAR(20) DEFAULT 'GLOBAL'"),
        ("compliance_flags", "TEXT DEFAULT '{}'"),
        ("created_by_admin_id", "VARCHAR(36)"),
    ]
    for col, definition in additions:
        if col not in cols:
            conn.execute(text(f"ALTER TABLE tenants ADD COLUMN {col} {definition}"))
            log.info("added tenants.%s", col)


try:
    with engine.begin() as conn:
        if DIALECT == "postgresql":
            run_postgres(conn)
        elif DIALECT == "sqlite":
            run_sqlite(conn)
        else:
            print(f"WARNING: unsupported dialect {DIALECT}; no changes made")
            sys.exit(1)

    print()
    print("=" * 50)
    print("Migration complete")
    print("=" * 50)
    print("Tables created or verified:")
    print("  - platform_settings")
    print("  - support_tickets")
    print("  - platform_messages")
    print("Tenant columns added or verified:")
    print("  - last_seen_at")
    print("  - health_status")
    print("  - region")
    print("  - compliance_flags")
    print("  - created_by_admin_id")
    print()
    print("Next: File 2 (platform_settings.py)")
except Exception as exc:
    print(f"ERROR: migration failed: {exc}")
    sys.exit(1)