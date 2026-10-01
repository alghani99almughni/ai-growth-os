"""Add call capture tables to migrations.py."""

import pathlib

path = pathlib.Path("migrations.py")
text = path.read_text(encoding="utf-8")

if "call_recordings" in text:
    print("SKIP: call tables already present")
    raise SystemExit(0)

anchor = (
    '            conn.execute(text("ALTER TABLE tenants '
    'ADD COLUMN IF NOT EXISTS agent_gender VARCHAR(10) DEFAULT \'female\'"))\n'
)

if anchor not in text:
    print("ERROR: anchor not found")
    raise SystemExit(1)

insert = (
    '            conn.execute(text("CREATE TABLE IF NOT EXISTS call_recordings '
    '(id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(36) NOT NULL, '
    'customer_id VARCHAR(36), call_record_id VARCHAR(36), '
    'customer_name VARCHAR(160) DEFAULT \'Guest\', '
    'customer_phone VARCHAR(32) DEFAULT \'\', '
    'channel VARCHAR(30) DEFAULT \'webrtc\', '
    'language_start VARCHAR(16) DEFAULT \'en\', '
    'language_end VARCHAR(16) DEFAULT \'en\', '
    'started_at TIMESTAMP, ended_at TIMESTAMP, '
    'duration_seconds INTEGER DEFAULT 0, turn_count INTEGER DEFAULT 0, '
    'status VARCHAR(30) DEFAULT \'in_progress\', '
    'outcome VARCHAR(40), intent_final VARCHAR(120), '
    'has_flags BOOLEAN DEFAULT FALSE, flag_count INTEGER DEFAULT 0, '
    'severity VARCHAR(20), '
    'avg_turn_latency_ms INTEGER DEFAULT 0, '
    'total_customer_audio_bytes INTEGER DEFAULT 0, '
    'total_ai_audio_bytes INTEGER DEFAULT 0, '
    'created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"))\n'
    '            conn.execute(text("CREATE INDEX IF NOT EXISTS '
    'ix_call_recordings_tenant_started ON call_recordings(tenant_id, started_at)"))\n'
    '            conn.execute(text("CREATE TABLE IF NOT EXISTS call_turns '
    '(id VARCHAR(36) PRIMARY KEY, recording_id VARCHAR(36) NOT NULL, '
    'turn_number INTEGER DEFAULT 1, '
    'ts_started TIMESTAMP, ts_ended TIMESTAMP, '
    'customer_text TEXT, customer_audio_url TEXT, '
    'customer_audio_ms INTEGER DEFAULT 0, stt_latency_ms INTEGER DEFAULT 0, '
    'intent VARCHAR(120), confidence FLOAT DEFAULT 0, '
    'language VARCHAR(16) DEFAULT \'en\', entities_json TEXT DEFAULT \'{}\', '
    'source VARCHAR(30) DEFAULT \'handler\', handler_name VARCHAR(80), '
    'handler_succeeded BOOLEAN DEFAULT FALSE, '
    'state_before VARCHAR(60), state_after VARCHAR(60), '
    'cleared_at_set BOOLEAN DEFAULT FALSE, '
    'ai_text TEXT, ai_audio_url TEXT, ai_audio_ms INTEGER DEFAULT 0, '
    'tts_latency_ms INTEGER DEFAULT 0, '
    'total_latency_ms INTEGER DEFAULT 0, tokens_used INTEGER DEFAULT 0, '
    'cost_usd FLOAT DEFAULT 0, error TEXT, '
    'created_at TIMESTAMP NOT NULL)"))\n'
    '            conn.execute(text("CREATE INDEX IF NOT EXISTS '
    'ix_call_turns_recording ON call_turns(recording_id, turn_number)"))\n'
    '            conn.execute(text("CREATE TABLE IF NOT EXISTS call_flags '
    '(id VARCHAR(36) PRIMARY KEY, recording_id VARCHAR(36) NOT NULL, '
    'turn_id VARCHAR(36), flag_type VARCHAR(50) NOT NULL, '
    'severity VARCHAR(20) DEFAULT \'warning\', message TEXT, '
    'details_json TEXT DEFAULT \'{}\', created_at TIMESTAMP NOT NULL)"))\n'
    '            conn.execute(text("CREATE INDEX IF NOT EXISTS '
    'ix_call_flags_recording ON call_flags(recording_id)"))\n'
    '            conn.execute(text("CREATE INDEX IF NOT EXISTS '
    'ix_call_flags_type ON call_flags(flag_type)"))\n'
)

text = text.replace(anchor, anchor + insert, 1)

path.write_text(text, encoding="utf-8")
print("Patched migrations.py")
print("New size:", len(text), "bytes")