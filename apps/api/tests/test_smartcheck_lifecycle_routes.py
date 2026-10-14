from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

import app.routes_security as routes
from app.routes_security import PassInput, VerifyTokenInput


def setup(monkeypatch, result=None):
    config = {"script_url": "https://script.google.com/macros/s/example/exec", "legacy_tenant_code": "TNT-101"}
    calls = []
    monkeypatch.setattr(routes, "tenant_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "admin_only", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "gate_staff", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "lifecycle_config", lambda *args, **kwargs: config)
    def call(cfg, user, action, **fields):
        calls.append((action, fields))
        return result if result is not None else {"status": "success", "ticketId": "TKT-ABC123", "visitorStatus": action, "qrToken": "q" * 64}
    monkeypatch.setattr(routes, "call_smartcheck", call)
    user = SimpleNamespace(id="u1", role="security", tenant_id="tenant-1", email="guard@example.com")
    return user, Mock(), calls


def test_list_passes_reads_smartcheck_source(monkeypatch):
    user, db, calls = setup(monkeypatch, {"status": "success", "visitors": [
        {"Ticket ID": "TKT-1", "Visitor Name": "Guest A", "Status": "PENDING", "Mobile": "12345"},
        {"Ticket ID": "TKT-2", "Visitor Name": "Guest B", "Status": "APPROVED", "Mobile": "67890"},
    ]})
    result = routes.list_passes("tenant-1", user=user, db=db, status="pending", limit=100)
    assert [x["id"] for x in result["items"]] == ["TKT-1"]
    assert result["items"][0]["visitor_name"] == "Guest A"
    assert calls[0][0] == "LIST_VISITORS"
    db.scalars.assert_not_called()


def test_create_pass_always_requires_human_approval(monkeypatch):
    user, db, calls = setup(monkeypatch)
    body = PassInput(visitor_name="Guest", visitor_mobile="1234567", needs_approval=False)
    with pytest.raises(HTTPException) as exc:
        routes.create_pass("tenant-1", body, user=user, db=db)
    assert exc.value.status_code == 422
    assert calls == []


def test_create_pass_writes_to_smartcheck_when_verified(monkeypatch):
    user, db, calls = setup(monkeypatch)
    body = PassInput(visitor_name="Guest", visitor_mobile="1234567", purpose="Meeting", destination="Office")
    result = routes.create_pass("tenant-1", body, user=user, db=db)
    assert result["id"] == "TKT-ABC123"
    assert result["status"] == "pending"
    assert calls[0][0] == "VISITOR_REQUEST"
    assert calls[0][1]["visitorName"] == "Guest"


@pytest.mark.parametrize(("fn", "action", "expected"), [
    (routes.approve_pass, "APPROVE_VISITOR", "approved"),
    (routes.check_in, "CHECK_IN", "checked_in"),
    (routes.check_out, "CHECK_OUT", "checked_out"),
    (routes.deny_pass, "REJECT_VISITOR", "denied"),
    (routes.cancel_pass, "CANCEL_VISITOR", "cancelled"),
])
def test_lifecycle_transitions_write_to_smartcheck(monkeypatch, fn, action, expected):
    user, db, calls = setup(monkeypatch)
    result = fn("tenant-1", "TKT-ABC123", user=user, db=db)
    assert result["status"] == expected
    assert calls[0][0] == action
    assert calls[0][1]["ticketId"] == "TKT-ABC123"


def test_qr_verification_uses_smartcheck_and_keeps_nested_contract(monkeypatch):
    user, db, calls = setup(monkeypatch, {"status": "success", "valid": True, "pass": {
        "ticketId": "TKT-ABC123", "visitorName": "Guest", "visitorMobile": "1234567",
        "purpose": "Meeting", "destination": "Office", "vehicleNumber": "", "qrToken": "q" * 64,
    }})
    result = routes.verify_token("tenant-1", VerifyTokenInput(token="q" * 64), user=user, db=db)
    assert result["valid"] is True
    assert result["pass"]["id"] == "TKT-ABC123"
    assert result["pass"]["visitor_name"] == "Guest"
    assert calls[0][0] == "VERIFY_TOKEN"


def test_qr_verification_rejects_unapproved_or_used_smartcheck_token(monkeypatch):
    user, db, calls = setup(monkeypatch, {"status": "success", "valid": False, "message": "Pass not approved"})
    with pytest.raises(HTTPException) as exc:
        routes.verify_token("tenant-1", VerifyTokenInput(token="q" * 64), user=user, db=db)
    assert exc.value.status_code == 409
