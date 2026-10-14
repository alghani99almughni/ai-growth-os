import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

import app.routes_smartcheck as smartcheck


def test_validate_script_url_accepts_deployed_apps_script_url():
    url = "https://script.google.com/macros/s/abc123/exec"
    assert smartcheck.validate_script_url(url) == url


@pytest.mark.parametrize("url", [
    "http://script.google.com/macros/s/abc/exec",
    "https://evil.example/macros/s/abc/exec",
    "https://script.google.com.evil.example/macros/s/abc/exec",
    "https://script.google.com/macros/s/abc/dev",
    "https://user:pass@script.google.com/macros/s/abc/exec",
    "https://script.google.com/macros/s/abc/exec?x=1",
])
def test_validate_script_url_rejects_untrusted_urls(url):
    with pytest.raises(HTTPException):
        smartcheck.validate_script_url(url)


def test_validate_drive_url_accepts_folder_url():
    url = "https://drive.google.com/drive/folders/folder-id"
    assert smartcheck.validate_drive_url(url) == url


@pytest.mark.parametrize("url", [
    "http://drive.google.com/drive/folders/id",
    "https://evil.example/drive/folders/id",
    "https://drive.google.com/file/d/id",
])
def test_validate_drive_url_rejects_invalid_urls(url):
    with pytest.raises(HTTPException):
        smartcheck.validate_drive_url(url)


def test_health_check_reports_ok_payload(monkeypatch):
    response = Mock()
    response.status = 200
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *args: None
    response.read.return_value = json.dumps({"status": "ok"}).encode()
    monkeypatch.setattr(smartcheck, "urlopen", lambda *args, **kwargs: response)
    assert smartcheck.check_script_health("https://script.google.com/macros/s/id/exec")["status"] == "reachable"


def test_health_check_does_not_claim_ready_for_unrecognized_payload(monkeypatch):
    response = Mock()
    response.status = 200
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *args: None
    response.read.return_value = json.dumps({"message": "hello"}).encode()
    monkeypatch.setattr(smartcheck, "urlopen", lambda *args, **kwargs: response)
    assert smartcheck.check_script_health("https://script.google.com/macros/s/id/exec")["status"] == "unverified"


class RoleValue:
    value = "SUPER_ADMIN"


def test_normalized_role_supports_enum_backed_role_values():
    assert smartcheck.normalized_role(RoleValue()) == "super_admin"


def test_validate_legacy_tenant_code_accepts_existing_code():
    assert smartcheck.validate_legacy_tenant_code(" TNT-101 ") == "TNT-101"


@pytest.mark.parametrize("code", ["TNT 101", "TNT/101", "TNT?101", "https://example.com"])
def test_validate_legacy_tenant_code_rejects_unsafe_values(code):
    with pytest.raises(HTTPException):
        smartcheck.validate_legacy_tenant_code(code)


def test_validate_legacy_tenant_code_allows_empty_mapping():
    assert smartcheck.validate_legacy_tenant_code("  ") is None



def test_lifecycle_verification_requires_active_legacy_tenant_mapping(monkeypatch):
    from types import SimpleNamespace

    row = SimpleNamespace(value_json=json.dumps({
        "script_url": "https://script.google.com/macros/s/example/exec",
        "legacy_tenant_code": "TNT-MISSING",
        "visitor_lifecycle_sync_ready": True,
    }))
    db = Mock()
    db.get.return_value = SimpleNamespace(id="tenant-1")
    db.commit = Mock()
    monkeypatch.setattr(smartcheck, "connection_setting", lambda db, tenant_id: row)

    def fake_call(config, user, action, **fields):
        if action == "PING":
            return {"status": "ok"}
        if action == "VALIDATE_TENANT":
            return {"status": "success", "valid": False}
        if action == "LIST_VISITORS":
            return {"status": "success", "visitors": []}
        if action == "VERIFY_TOKEN":
            return {"status": "success", "valid": False}
        raise AssertionError(action)

    monkeypatch.setattr(smartcheck, "call_smartcheck", fake_call)
    user = SimpleNamespace(id="platform-user")

    with pytest.raises(HTTPException) as exc:
        smartcheck.verify_smartcheck_lifecycle("tenant-1", user=user, db=db)

    assert exc.value.status_code == 409
    assert json.loads(row.value_json)["visitor_lifecycle_sync_ready"] is False
    assert "active tenant mapping" in json.loads(row.value_json)["lifecycle_verification_error"]


def test_lifecycle_verification_enables_only_after_all_probes(monkeypatch):
    from types import SimpleNamespace

    row = SimpleNamespace(value_json=json.dumps({
        "script_url": "https://script.google.com/macros/s/example/exec",
        "legacy_tenant_code": "TNT-101",
    }))
    db = Mock()
    db.get.return_value = SimpleNamespace(id="tenant-1")
    db.commit = Mock()
    monkeypatch.setattr(smartcheck, "connection_setting", lambda db, tenant_id: row)
    actions = []

    def fake_call(config, user, action, **fields):
        actions.append(action)
        return {
            "PING": {"status": "ok"},
            "VALIDATE_TENANT": {"status": "success", "valid": True},
            "LIST_VISITORS": {"status": "success", "visitors": []},
            "VERIFY_TOKEN": {"status": "success", "valid": False},
        }[action]

    monkeypatch.setattr(smartcheck, "call_smartcheck", fake_call)
    user = SimpleNamespace(id="platform-user")
    result = smartcheck.verify_smartcheck_lifecycle("tenant-1", user=user, db=db)

    assert result["visitor_lifecycle_sync_ready"] is True
    assert result["checks"]["tenant_mapping"] == "passed"
    assert actions == ["PING", "VALIDATE_TENANT", "LIST_VISITORS", "VERIFY_TOKEN"]
    assert json.loads(row.value_json)["visitor_lifecycle_sync_ready"] is True
