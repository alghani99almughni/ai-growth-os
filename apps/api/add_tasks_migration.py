"""Create platform_tasks table for calendar follow-up tasks."""
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
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS platform_tasks (
                    id VARCHAR(36) PRIMARY KEY,
                    title VARCHAR(300) NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    due_at TIMESTAMP NOT NULL,
                    tenant_id VARCHAR(36),
                    kind VARCHAR(40) NOT NULL DEFAULT 'followup',
                    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
                    status VARCHAR(30) NOT NULL DEFAULT 'pending',
                    created_by VARCHAR(36),
                    created_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_tasks_due ON platform_tasks(due_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_tasks_status ON platform_tasks(status)"))
        elif DIALECT == "sqlite":
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS platform_tasks (
                    id VARCHAR(36) PRIMARY KEY,
                    title VARCHAR(300) NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    due_at DATETIME NOT NULL,
                    tenant_id VARCHAR(36),
                    kind VARCHAR(40) NOT NULL DEFAULT 'followup',
                    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
                    status VARCHAR(30) NOT NULL DEFAULT 'pending',
                    created_by VARCHAR(36),
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_tasks_due ON platform_tasks(due_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_tasks_status ON platform_tasks(status)"))
        else:
            print(f"unsupported dialect {DIALECT}")
            sys.exit(1)

    print("platform_tasks ready")
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)