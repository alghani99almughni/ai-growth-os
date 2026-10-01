"""Add the missing updated_by column to platform_settings.

The Session 17a migration used ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
which SQLite does not support. The column was never added. This script
adds it properly for both SQLite and Postgres.
"""
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
            conn.execute(text(
                "ALTER TABLE platform_settings "
                "ADD COLUMN IF NOT EXISTS updated_by VARCHAR(36)"
            ))
            print("added updated_by (postgres)")
        elif DIALECT == "sqlite":
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(platform_settings)"))}
            print(f"current columns: {sorted(cols)}")
            if "updated_by" not in cols:
                conn.execute(text(
                    "ALTER TABLE platform_settings ADD COLUMN updated_by VARCHAR(36)"
                ))
                print("added updated_by")
            else:
                print("updated_by already present")
        else:
            print(f"unsupported dialect: {DIALECT}")
            sys.exit(1)

    print()
    print("Done. Now run the verify command.")
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)