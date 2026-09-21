from .db import Base,engine
from . import models,models_growth,models_ai
from sqlalchemy import text

def ensure_schema():
    Base.metadata.create_all(bind=engine)
    # Lightweight compatibility migration for deployments created before call handoff fields existed.
    with engine.begin() as conn:
        dialect=engine.dialect.name
        if dialect=="postgresql":
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
        elif dialect=="sqlite":
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
