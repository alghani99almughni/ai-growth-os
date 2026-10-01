"""Add duration_minutes and all_day to platform_tasks."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sqlalchemy import text
from app.db import engine

DIALECT = engine.dialect.name
print(f"Dialect: {DIALECT}")

try:
    with engine.begin() as conn:
        if DIALECT == "postgresql":
            conn.execute(text("ALTER TABLE platform_tasks ADD COLUMN IF NOT EXISTS duration_minutes INTEGER DEFAULT 30"))
            conn.execute(text("ALTER TABLE platform_tasks ADD COLUMN IF NOT EXISTS all_day BOOLEAN DEFAULT FALSE"))
        elif DIALECT == "sqlite":
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(platform_tasks)"))}
            if "duration_minutes" not in cols:
                conn.execute(text("ALTER TABLE platform_tasks ADD COLUMN duration_minutes INTEGER DEFAULT 30"))
                print("added duration_minutes")
            if "all_day" not in cols:
                conn.execute(text("ALTER TABLE platform_tasks ADD COLUMN all_day BOOLEAN DEFAULT 0"))
                print("added all_day")
        else:
            print(f"unsupported dialect: {DIALECT}")
            sys.exit(1)
    print("migration complete")
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)