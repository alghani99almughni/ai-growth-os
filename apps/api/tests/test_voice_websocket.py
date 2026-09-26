from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app.main as main


class FakeCustomer:
    name = "Test Customer"
    phone = "9000000000"


class FakeCall:
    id = "call-test"
    tenant_id = "tenant-test"
    customer = FakeCustomer()
    source = "pwa_voice"
    status = "ringing"
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    transcript = None
    resolution = None
    answered_at = None
    ended_at = None
    duration_seconds = None
    language = None
    ai_turns = 0
    knowledge_hits = 0


class FakeTenant:
    id = "tenant-test"
    name = "Test Business"
    timezone = "Asia/Kolkata"
    address = None
    phone = None
    website = None


class FakeDB:
    def __init__(self):
        self.call = FakeCall()
        self.tenant = FakeTenant()

    def get(self, model, ident):
        if ident == self.call.id:
            return self.call
        if ident == self.tenant.id:
            return self.tenant
        return None

    def commit(self):
        pass

    def close(self):
        pass


class FailingGateway:
    def __init__(self, adapters):
        pass

    async def connect_with_failover(self, *args, **kwargs):
        raise RuntimeError("simulated provider outage")


def test_public_voice_provider_failure_is_structured_not_http_500(monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", FakeDB)
    monkeypatch.setattr(main, "knowledge_context", lambda db, tenant_id: "")
    monkeypatch.setattr(main, "tenant_policy", lambda db, tenant_id: {})
    monkeypatch.setattr(main, "policy_context", lambda policy: "")
    monkeypatch.setattr(main, "capability_enabled", lambda policy, capability, default: default)
    monkeypatch.setattr(main, "VoiceGateway", FailingGateway)

    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/public/voice/call-test") as ws:
            message = ws.receive_json()
            assert message["type"] == "error"
            assert message["code"] == "ai_provider_unavailable"
            assert message["recoverable"] is True
