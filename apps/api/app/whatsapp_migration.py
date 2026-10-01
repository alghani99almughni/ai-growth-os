"""One-shot migration to make WhatsApp two-channel capable.

Changes:
    1. Drop UNIQUE(tenant_id) on tenant_whatsapp_connections.tenant_id
    2. Add UNIQUE(tenant_id, provider)
    3. Backfill whatsapp_priority TenantSetting from each tenant's
       existing connection provider

Idempotent: safe to run on every startup.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)


def ensure_two_channel_whatsapp(engine) -> None:
    """Run once per process. Never raises."""
    dialect = engine.dialect.name
    try:
        with engine.begin() as conn:
            if dialect == "postgresql":
                _pg(conn)
            elif dialect == "sqlite":
                _sqlite(conn)
    except Exception as exc:
        logger.warning("whatsapp two-channel migration failed: %s", exc)


def _pg(conn) -> None:
    # Postgres cannot drop a unique constraint by column name directly;
    # find and drop it, then create the compound one.
    conn.execute(text("""
        DO $$
        DECLARE cname text;
        BEGIN
            SELECT constraint_name INTO cname
            FROM information_schema.table_constraints
            WHERE table_name = 'tenant_whatsapp_connections'
              AND constraint_type = 'UNIQUE'
            LIMIT 1;
            IF cname IS NOT NULL THEN
                EXECUTE 'ALTER TABLE tenant_whatsapp_connections DROP CONSTRAINT ' || quote_ident(cname);
            END IF;
        END $$;
    """))
    # Drop any leftover unique index
    conn.execute(text("DROP INDEX IF EXISTS ix_tenant_whatsapp_connections_tenant_id"))
    # Non-unique index on tenant_id (lookups still fast)
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_twc_tenant ON tenant_whatsapp_connections(tenant_id)"))
    # The compound unique constraint
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ux_twc_tenant_provider'
            ) THEN
                ALTER TABLE tenant_whatsapp_connections
                ADD CONSTRAINT ux_twc_tenant_provider UNIQUE (tenant_id, provider);
            END IF;
        END $$;
    """))
    _backfill_priority_pg(conn)


def _sqlite(conn) -> None:
    # SQLite: check if the schema already has the compound index.
    # SQLAlchemy on SQLite names the unique constraint after the column.
    rows = conn.execute(text("PRAGMA index_list('tenant_whatsapp_connections')")).fetchall()
    has_compound = False
    for r in rows:
        # r = (seq, name, unique, origin, partial)
        name = r[1] if len(r) > 1 else None
        if not name:
            continue
        cols = [c[2] for c in conn.execute(
            text(f"PRAGMA index_info('{name}')")
        ).fetchall()]
        if set(cols) == {"tenant_id", "provider"} and r[2]:
            has_compound = True
            break

    # Drop the old single-column unique index if it exists
    for r in rows:
        name = r[1] if len(r) > 1 else None
        if not name:
            continue
        cols = [c[2] for c in conn.execute(
            text(f"PRAGMA index_info('{name}')")
        ).fetchall()]
        if cols == ["tenant_id"] and r[2]:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
            except Exception:
                pass

    if not has_compound:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_twc_tenant_provider "
            "ON tenant_whatsapp_connections(tenant_id, provider)"
        ))

    _backfill_priority_sqlite(conn)


def _backfill_priority_pg(conn) -> None:
    rows = conn.execute(text("""
        SELECT tenant_id, provider
        FROM tenant_whatsapp_connections
        WHERE status = 'connected'
    """)).fetchall()
    for tenant_id, provider in rows:
        conn.execute(text("""
            INSERT INTO tenant_settings (id, tenant_id, key, value_json, created_at)
            VALUES (:id, :tid, 'whatsapp_priority', :vj, :now)
            ON CONFLICT DO NOTHING
        """), {
            "id": _new_id(), "tid": tenant_id,
            "vj": json.dumps({"priority": (provider or "openwa").lower()}),
            "now": datetime.utcnow(),
        })


def _backfill_priority_sqlite(conn) -> None:
    rows = conn.execute(text("""
        SELECT tenant_id, provider
        FROM tenant_whatsapp_connections
        WHERE status = 'connected'
    """)).fetchall()
    for tenant_id, provider in rows:
        # Only insert if no priority row exists yet
        existing = conn.execute(text(
            "SELECT id FROM tenant_settings "
            "WHERE tenant_id = :tid AND key = 'whatsapp_priority'"
        ), {"tid": tenant_id}).fetchone()
        if existing:
            continue
        conn.execute(text("""
            INSERT INTO tenant_settings (id, tenant_id, key, value_json, created_at)
            VALUES (:id, :tid, 'whatsapp_priority', :vj, :now)
        """), {
            "id": _new_id(), "tid": tenant_id,
            "vj": json.dumps({"priority": (provider or "openwa").lower()}),
            "now": datetime.utcnow(),
        })


def _new_id() -> str:
    import uuid
    return str(uuid.uuid4())