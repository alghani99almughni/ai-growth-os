import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

import app.routes_smartcheck_public as public_routes
from app.routes_smartcheck_public import PublicVisitorRequest


class FakeResponse:
    status = 200

    def __init__(self, payload, url="https://script.googleusercontent.com/macros/echo"):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def geturl(self):
        return self.url

    def read(self, limit):
        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


def test_public_request_posts_to_smartcheck_with_server_secret(monkeypatch):
    opener = FakeOpener(FakeResponse({
        "status": "success", "ticketId": "TKT-ABC123", "statusLabel": "PENDING"
    }))
    monkeypatch.setattr(public_routes, "build_opener", lambda *args: opener)
    body = PublicVisitorRequest(
        visitor_name="Guest", visitor_mobile="+919876543210",
        purpose="Meeting", destination="Reception", vehicle_number="TS09AB1234",
    )

    result = public_routes._submit_to_smartcheck(
        {"script_url": "https://script.google.com/macros/s/id/exec", "legacy_tenant_code": "TNT-101"},
        "server-only-secret", body,
    )

    posted = json.loads(opener.request.data.decode("utf-8"))
    assert posted["action"] == "VISITOR_REQUEST"
    assert posted["bridgeSecret"] == "server-only-secret"
    assert posted["actorRole"] == "VISITOR"
    assert posted["actorTenantId"] == "TNT-101"
    assert posted["tenantId"] == "TNT-101"
    assert posted["visitorName"] == "Guest"
    assert result["ticket_id"] == "TKT-ABC123"
    assert result["status"] == "PENDING"
    assert opener.timeout == 10


def test_public_request_rejects_untrusted_redirect(monkeypatch):
    opener = FakeOpener(FakeResponse(
        {"status": "success", "ticketId": "TKT-ABC123"},
        url="https://evil.example/collect",
    ))
    monkeypatch.setattr(public_routes, "build_opener", lambda *args: opener)
    body = PublicVisitorRequest(visitor_name="Guest", visitor_mobile="1234567")

    with pytest.raises(HTTPException) as exc:
        public_routes._submit_to_smartcheck(
            {"script_url": "https://script.google.com/macros/s/id/exec", "legacy_tenant_code": "TNT-101"},
            "server-only-secret", body,
        )
    assert exc.value.status_code == 502


def test_public_request_does_not_claim_saved_without_ticket(monkeypatch):
    opener = FakeOpener(FakeResponse({"status": "success", "message": "ok"}))
    monkeypatch.setattr(public_routes, "build_opener", lambda *args: opener)
    body = PublicVisitorRequest(visitor_name="Guest", visitor_mobile="1234567")

    with pytest.raises(HTTPException) as exc:
        public_routes._submit_to_smartcheck(
            {"script_url": "https://script.google.com/macros/s/id/exec", "legacy_tenant_code": "TNT-101"},
            "server-only-secret", body,
        )
    assert exc.value.status_code == 502
