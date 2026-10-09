import asyncio
from types import SimpleNamespace

import pytest

from app import routes_webcall


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []
        self.application_state = SimpleNamespace(value="connected")
        self.closed_code = None

    async def accept(self):
        self.sent.append(("accepted", None))

    async def send_json(self, payload):
        self.sent.append(("json", payload))

    async def close(self, code=None):
        self.closed_code = code

    async def receive_json(self):
        return next(self.messages)


class FakeDB:
    def __init__(self, call, tenant, customer):
        self.call = call
        self.tenant = tenant
        self.customer = customer
        self.closed = False

    def get(self, model, key):
        name = getattr(model, "__name__", "")
        if name == "CallRecord":
            return self.call
        if name == "Tenant":
            return self.tenant
        if name == "Customer":
            return self.customer
        return None

    def scalars(self, statement):
        return SimpleNamespace(all=lambda: [])

    def commit(self):
        pass

    def close(self):
        self.closed = True

    def rollback(self):
        pass


class FakeProvider:
    name = "fake"


class FakeSession:
    pass


class FakeGateway:
    def __init__(self, adapters):
        self.adapters = adapters

    async def connect_with_failover(self, providers, system_instruction, tools, state):
        return FakeProvider(), FakeSession()

    def adapter_for(self, provider):
        return SimpleNamespace(
            send_text=self.send_text,
            close=self.close,
        )

    async def send_text(self, session, text):
        self.greeting = text

    async def close(self, session):
        pass


class FakeRuntime:
    instances = []

    def __init__(self, websocket, call_id, providers, system_instruction):
        self.websocket = websocket
        self.call_id = call_id
        self.providers = providers
        self.system_instruction = system_instruction
        self.gateway = None
        self.state = SimpleNamespace()
        self.provider = None
        self.session = None
        self.provider_task = None
        self.closed = False
        self.setup_called_with = None
        FakeRuntime.instances.append(self)

    async def setup_peer(self, offer):
        self.setup_called_with = offer
        await self.websocket.send_json({"type": "answer", "sdp": "fake-answer", "sdp_type": "answer"})

    async def provider_loop(self):
        await asyncio.sleep(0)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_public_webcall_offer_first_signaling_and_provider_connection(monkeypatch):
    call = SimpleNamespace(
        id="call-1",
        source="pwa_voice",
        tenant_id="tenant-1",
        customer_id="customer-1",
        status="ringing",
        started_at=routes_webcall.datetime.utcnow(),
        answered_at=None,
        ended_at=None,
    )
    tenant = SimpleNamespace(
        id="tenant-1",
        name="Demo Business",
        address="Test Address",
        phone="9999999999",
        website="https://example.test",
    )
    customer = SimpleNamespace(id="customer-1", name="Syed Shukur", phone="9999999999", gender=None)
    db = FakeDB(call, tenant, customer)
    websocket = FakeWebSocket([
        {"type": "offer", "sdp": "fake-offer", "sdp_type": "offer"},
        {"type": "hangup"},
    ])

    monkeypatch.setattr(routes_webcall, "SessionLocal", lambda: db)
    monkeypatch.setattr(routes_webcall, "_verify_room_token", lambda token, call_id: True)
    monkeypatch.setattr(routes_webcall, "_providers", lambda db, tenant: [FakeProvider()])
    monkeypatch.setattr(routes_webcall, "knowledge_context", lambda db, tenant_id: "approved context")
    monkeypatch.setattr(routes_webcall, "tenant_policy", lambda db, tenant_id: {})
    monkeypatch.setattr(routes_webcall, "WebCallRuntime", FakeRuntime)
    monkeypatch.setattr(routes_webcall, "VoiceGateway", FakeGateway)

    await routes_webcall.public_webcall(websocket, "call-1", "valid-token")

    runtime = FakeRuntime.instances[-1]
    assert runtime.setup_called_with["type"] == "offer"
    assert runtime.provider.name == "fake"
    assert call.status == "completed"
    assert call.answered_at is not None
    assert runtime.closed is True

    payloads = [payload for kind, payload in websocket.sent if kind == "json"]
    assert payloads[0]["type"] == "status"
    assert payloads[0]["status"] == "signaling_ready"
    assert any(p.get("type") == "answer" for p in payloads)
    assert any(p.get("type") == "status" and p.get("status") == "ai_connected" for p in payloads)


@pytest.mark.asyncio
async def test_public_webcall_rejects_non_offer_as_first_message(monkeypatch):
    call = SimpleNamespace(
        id="call-2",
        source="pwa_voice",
        tenant_id="tenant-1",
        customer_id=None,
        status="ringing",
        started_at=routes_webcall.datetime.utcnow(),
        answered_at=None,
        ended_at=None,
    )
    tenant = SimpleNamespace(id="tenant-1", name="Demo", address=None, phone=None, website=None)
    db = FakeDB(call, tenant, None)
    websocket = FakeWebSocket([{"type": "diagnostic", "event": "client_ice_policy"}])

    monkeypatch.setattr(routes_webcall, "SessionLocal", lambda: db)
    monkeypatch.setattr(routes_webcall, "_verify_room_token", lambda token, call_id: True)
    monkeypatch.setattr(routes_webcall, "_providers", lambda db, tenant: [FakeProvider()])
    monkeypatch.setattr(routes_webcall, "knowledge_context", lambda db, tenant_id: "")
    monkeypatch.setattr(routes_webcall, "tenant_policy", lambda db, tenant_id: {})
    monkeypatch.setattr(routes_webcall, "WebCallRuntime", FakeRuntime)

    await routes_webcall.public_webcall(websocket, "call-2", "valid-token")

    payloads = [payload for kind, payload in websocket.sent if kind == "json"]
    assert payloads[-1]["type"] == "error"
    assert payloads[-1]["code"] == "offer_required"
    assert call.status == "completed"
