import json
from types import SimpleNamespace
from unittest.mock import Mock

import app.smartcheck_bridge as bridge


def test_lifecycle_config_is_disabled_when_visitor_data_uses_postgresql():
    db = Mock()
    db.scalar.return_value = SimpleNamespace(value_json=json.dumps({
        "script_url": "https://script.google.com/macros/s/example/exec",
        "legacy_tenant_code": "TNT-101",
        "visitor_lifecycle_sync_ready": True,
    }))
    assert bridge.lifecycle_config(db, "tenant-1") is None


def test_lifecycle_config_never_reads_or_requires_bridge_secret(monkeypatch):
    monkeypatch.delenv("AI_GROWTH_OS_BRIDGE_SECRET", raising=False)
    db = Mock()
    assert bridge.lifecycle_config(db, "tenant-1") is None
    db.scalar.assert_not_called()


def test_lifecycle_config_never_enables_untrusted_or_legacy_script_url():
    db = Mock()
    db.scalar.return_value = SimpleNamespace(value_json=json.dumps({
        "script_url": "https://evil.example/macros/s/example/exec",
        "legacy_tenant_code": "TNT-101",
        "visitor_lifecycle_sync_ready": True,
    }))
    assert bridge.lifecycle_config(db, "tenant-1") is None


def test_legacy_sheet_mapping_helpers_remain_compatible():
    row = {
        "Ticket ID": "TKT-ABC123", "Visitor Name": "Guest", "Mobile": "+919876543210",
        "Purpose": "Meeting", "Target Destination": "Reception", "Vehicle Number": "TS09AB1234",
        "Status": "CHECKED_IN", "QR Token": "secret-token", "Date": "2026-10-14",
    }
    result = bridge.pass_from_sheet(row, "tenant-1")
    assert result["id"] == "TKT-ABC123"
    assert result["tenant_id"] == "tenant-1"
    assert result["status"] == "checked_in"
    assert result["qr_token"] == "secret-token"
    assert result["visitor_name"] == "Guest"


def test_sheet_status_mapping_is_closed_to_known_transitions():
    assert bridge.pass_from_sheet({"Status": "REJECTED"}, "t")["status"] == "denied"
    assert bridge.pass_from_sheet({"Status": "CHECKED_OUT"}, "t")["status"] == "checked_out"
    assert bridge.pass_from_sheet({"Status": "UNKNOWN"}, "t")["status"] == "pending"
