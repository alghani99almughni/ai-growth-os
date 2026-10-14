import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

import app.smartcheck_bridge as bridge


def test_lifecycle_config_is_disabled_without_explicit_verified_flag():
    db = Mock()
    db.scalar.return_value = SimpleNamespace(value_json=json.dumps({
        "script_url": "https://script.google.com/macros/s/example/exec",
        "legacy_tenant_code": "TNT-101",
    }))
    assert bridge.lifecycle_config(db, "tenant-1") is None


def test_lifecycle_config_requires_server_secret(monkeypatch):
    monkeypatch.delenv("AI_GROWTH_OS_BRIDGE_SECRET", raising=False)
    db = Mock()
    db.scalar.return_value = SimpleNamespace(value_json=json.dumps({
        "script_url": "https://script.google.com/macros/s/example/exec",
        "legacy_tenant_code": "TNT-101",
        "visitor_lifecycle_sync_ready": True,
    }))
    with pytest.raises(HTTPException) as exc:
        bridge.lifecycle_config(db, "tenant-1")
    assert exc.value.status_code == 503


def test_lifecycle_config_rejects_untrusted_script_url():
    db = Mock()
    db.scalar.return_value = SimpleNamespace(value_json=json.dumps({
        "script_url": "https://evil.example/macros/s/example/exec",
        "legacy_tenant_code": "TNT-101",
        "visitor_lifecycle_sync_ready": True,
    }))
    with pytest.raises(HTTPException) as exc:
        bridge.lifecycle_config(db, "tenant-1")
    assert exc.value.status_code == 503


def test_sheet_visitor_maps_to_existing_dashboard_contract():
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


def test_smartcheck_request_keeps_bridge_secret_server_side(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def geturl(self): return "https://script.googleusercontent.com/macros/echo"
        def read(self, limit): return b'{"status":"success","visitors":[]}'

    class Opener:
        def open(self, request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return Response()

    monkeypatch.setenv("AI_GROWTH_OS_BRIDGE_SECRET", "server-only-secret")
    monkeypatch.setattr(bridge, "build_opener", lambda *args: Opener())
    user = SimpleNamespace(role="tenant_admin", tenant_id="tenant-1", email="admin@example.com", id="user-1")
    result = bridge.call_smartcheck({
        "script_url": "https://script.google.com/macros/s/example/exec",
        "legacy_tenant_code": "TNT-101",
    }, user, "LIST_VISITORS")
    assert result["status"] == "success"
    assert captured["payload"]["bridgeSecret"] == "server-only-secret"
    assert captured["payload"]["actorRole"] == "TENANT_ADMIN"
    assert captured["payload"]["tenantId"] == "TNT-101"
    assert captured["timeout"] == 12


def test_sheet_status_mapping_is_closed_to_known_transitions():
    assert bridge.pass_from_sheet({"Status": "REJECTED"}, "t")["status"] == "denied"
    assert bridge.pass_from_sheet({"Status": "CHECKED_OUT"}, "t")["status"] == "checked_out"
    assert bridge.pass_from_sheet({"Status": "UNKNOWN"}, "t")["status"] == "pending"
