"""Add offline_calls table to migrations.py."""

import pathlib

path = pathlib.Path("migrations.py")
text = path.read_text(encoding="utf-8")

if "offline_calls" in text:
    print("SKIP: offline_calls already present")
    raise SystemExit(0)

anchor = (
    '            conn.execute(text("ALTER TABLE tenants '
    'ADD COLUMN IF NOT EXISTS agent_gender VARCHAR(10) DEFAULT \'female\'"))\n'
)

if anchor not in text:
    print("ERROR: anchor not found")
    raise SystemExit(1)

insert = (
    '            conn.execute(text("CREATE TABLE IF NOT EXISTS offline_calls '
    '(id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, '
    'customer_name VARCHAR(160) DEFAULT \'Guest\', '
    'customer_phone VARCHAR(32) DEFAULT \'\', '
    'customer_email VARCHAR(320), '
    'channel VARCHAR(30) DEFAULT \'widget_offline\', '
    'language VARCHAR(16) DEFAULT \'en\', '
    'call_started_at TIMESTAMP, '
    'audio_url TEXT, audio_size_bytes INTEGER DEFAULT 0, '
    'audio_duration_seconds INTEGER DEFAULT 0, '
    'transcript TEXT, reply TEXT, intent VARCHAR(120), '
    'language_detected VARCHAR(16), '
    'whatsapp_ok BOOLEAN DEFAULT FALSE, '
    'sms_ok BOOLEAN DEFAULT FALSE, '
    'email_ok BOOLEAN DEFAULT FALSE, '
    'lead_id VARCHAR(36), '
    'status VARCHAR(30) DEFAULT \'received\', '
    'error TEXT, '
    'created_at TIMESTAMP NOT NULL, processed_at TIMESTAMP)"))\n'
    '            conn.execute(text("CREATE INDEX IF NOT EXISTS '
    'ix_offline_calls_tenant_status ON offline_calls(tenant_id, status)"))\n'
    '            conn.execute(text("CREATE INDEX IF NOT EXISTS '
    'ix_offline_calls_status ON offline_calls(status)"))\n'
)

text = text.replace(anchor, anchor + insert, 1)

path.write_text(text, encoding="utf-8")
print("Patched migrations.py")
print("New size:", len(text), "bytes")