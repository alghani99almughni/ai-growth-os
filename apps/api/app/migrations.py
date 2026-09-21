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
