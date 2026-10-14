"""Focused tests for security module entitlement and tenant isolation."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

import app.routes_security as security_routes
from app.routes_security import PassInput, VisitorRequestInput, tenant_access


def test_pass_input_accepts_supported_industry():
    body = PassInput(visitor_name="Guest", industry="school")
    assert body.industry == "school"
    assert body.needs_approval is True


def test_ai_request_has_no_approval_override():
    body = VisitorRequestInput(visitor_name="Guest", purpose="Parent meeting")
    assert body.visitor_name == "Guest"
    assert not hasattr(body, "needs_approval")


def test_regular_user_cannot_select_another_tenant():
    db = Mock()
    user = SimpleNamespace(tenant_id="tenant-a", role="owner")
    with pytest.raises(HTTPException) as exc:
        tenant_access("tenant-b", user, db)
    assert exc.value.status_code == 403
    db.get.assert_not_called()


def test_security_module_is_opt_in_when_no_feature_configured():
    db = Mock()
    db.get.return_value = SimpleNamespace(status="active")
    db.scalar.return_value = None
    user = SimpleNamespace(tenant_id="tenant-a", role="owner")
    with pytest.raises(HTTPException) as exc:
        tenant_access("tenant-a", user, db)
    assert exc.value.status_code == 403
    assert "disabled" in exc.value.detail.lower()


def test_platform_admin_still_requires_module_enabled_for_target_tenant():
    db = Mock()
    db.get.return_value = SimpleNamespace(status="active")
    db.scalar.side_effect = [
        SimpleNamespace(value_json=json.dumps({"security_visitor_management": True})),
        None,
    ]
    user = SimpleNamespace(tenant_id="platform-tenant", role="platform_admin")
    tenant_access("tenant-a", user, db)


def test_create_pass_rejects_approval_bypass(monkeypatch):
    monkeypatch.setattr(security_routes, "tenant_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(security_routes, "admin_only", lambda user: None)
    user = SimpleNamespace(id="user-1", role="owner")
    body = PassInput(visitor_name="Guest", needs_approval=False)
    with pytest.raises(HTTPException) as exc:
        security_routes.create_pass("tenant-a", body, user=user, db=Mock())
    assert exc.value.status_code == 422
    assert "human approval" in exc.value.detail.lower()


def test_verify_token_returns_stable_nested_pass_contract(monkeypatch):
    """The dashboard consumes {valid: true, pass: {...}} from QR verification."""
    from datetime import datetime
    from app.routes_security import VerifyTokenInput

    monkeypatch.setattr(security_routes, "tenant_access", lambda *args, **kwargs: None)
    visitor_pass = SimpleNamespace(
        id="pass-1", tenant_id="tenant-a", site_id=None, visitor_name="Guest",
        visitor_mobile="", purpose="Meeting", destination="Office", vehicle_number="",
        industry="apartment", status="approved", expires_at=None,
        created_at=datetime(2026, 1, 1), checked_in_at=None, checked_out_at=None,
    )
    db = Mock()
    db.scalar.return_value = visitor_pass
    user = SimpleNamespace(id="user-1", role="security", tenant_id="tenant-a")

    result = security_routes.verify_token(
        "tenant-a", VerifyTokenInput(token="x" * 32), user=user, db=db
    )

    assert result["valid"] is True
    assert result["pass"]["visitor_name"] == "Guest"
    assert result["pass"]["status"] == "approved"
    db.commit.assert_called_once()



def test_security_role_cannot_approve_a_pass(monkeypatch):
    monkeypatch.setattr(security_routes, "tenant_access", lambda *args, **kwargs: None)
    user = SimpleNamespace(id="guard-1", role="security", tenant_id="tenant-a")
    db = Mock()
    with pytest.raises(HTTPException) as exc:
        security_routes.approve_pass("tenant-a", "pass-1", user=user, db=db)
    assert exc.value.status_code == 403
    db.scalar.assert_not_called()


def test_check_in_requires_approved_unused_pass_and_records_audit_event(monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(security_routes, "tenant_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(security_routes, "gate_staff", lambda user: None)
    events = []
    monkeypatch.setattr(security_routes, "event", lambda db, tenant, pass_id, actor, kind, details=None: events.append(kind))
    visitor_pass = SimpleNamespace(
        id="pass-1", tenant_id="tenant-a", status="approved", expires_at=None,
        checked_in_at=None, checked_out_at=None, created_at=datetime.utcnow(),
    )
    db = Mock()
    db.scalar.return_value = visitor_pass
    user = SimpleNamespace(id="guard-1", role="security", tenant_id="tenant-a")

    result = security_routes.check_in("tenant-a", "pass-1", user=user, db=db)

    assert result["status"] == "checked_in"
    assert visitor_pass.checked_in_at is not None
    assert events == ["visitor_checked_in"]
    db.commit.assert_called_once()


def test_check_in_rejects_pending_pass_without_audit_success_event(monkeypatch):
    monkeypatch.setattr(security_routes, "tenant_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(security_routes, "gate_staff", lambda user: None)
    events = []
    monkeypatch.setattr(security_routes, "event", lambda db, tenant, pass_id, actor, kind, details=None: events.append(kind))
    visitor_pass = SimpleNamespace(id="pass-1", tenant_id="tenant-a", status="pending", expires_at=None)
    db = Mock()
    db.scalar.return_value = visitor_pass
    user = SimpleNamespace(id="guard-1", role="security", tenant_id="tenant-a")

    with pytest.raises(HTTPException) as exc:
        security_routes.check_in("tenant-a", "pass-1", user=user, db=db)

    assert exc.value.status_code == 409
    assert events == []
    db.commit.assert_not_called()


def test_check_out_requires_checked_in_state_and_records_audit_event(monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(security_routes, "tenant_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(security_routes, "gate_staff", lambda user: None)
    events = []
    monkeypatch.setattr(security_routes, "event", lambda db, tenant, pass_id, actor, kind, details=None: events.append(kind))
    visitor_pass = SimpleNamespace(
        id="pass-1", tenant_id="tenant-a", status="checked_in", expires_at=None,
        checked_in_at=datetime.utcnow(), checked_out_at=None, created_at=datetime.utcnow(),
    )
    db = Mock()
    db.scalar.return_value = visitor_pass
    user = SimpleNamespace(id="guard-1", role="security", tenant_id="tenant-a")

    result = security_routes.check_out("tenant-a", "pass-1", user=user, db=db)

    assert result["status"] == "checked_out"
    assert visitor_pass.checked_out_at is not None
    assert events == ["visitor_checked_out"]
    db.commit.assert_called_once()
