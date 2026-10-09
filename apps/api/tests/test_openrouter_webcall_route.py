import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import routes_openrouter_webcall as route


class FakeDB:
    def __init__(self, call, tenant, customer):
        self.call = call
        self.rows = {"CallRecord": call, "Tenant": tenant, "Customer": customer}
        self.closed = False

    def get(self, model, key):
        return self.rows.get(model.__name__)

    def close(self):
        self.closed = True

    def commit(self):
        pass


class FakeTurnService:
    def __init__(self):
        pass

    async def respond(self, system_prompt, history, user_text):
        assert system_prompt == "tenant prompt"
        assert user_text == "Hi"
        return "Hello from OpenRouter"


def setup_route(monkeypatch, call_status="ringing"):
    call = SimpleNamespace(
        id="call-1", source="pwa_voice", tenant_id="tenant-1",
        customer_id="customer-1", status=call_status, started_at=datetime.utcnow(),
    )
    tenant = SimpleNamespace(id="tenant-1", name="Demo")
    customer = SimpleNamespace(id="customer-1", name="Customer")
    db = FakeDB(call, tenant, customer)
    monkeypatch.setattr(route, "SessionLocal", lambda: db)
    monkeypatch.setattr(route, "_verify_room_token", lambda token, call_id: token == "valid")
    monkeypatch.setattr(route, "knowledge_context", lambda db, tenant_id: "approved facts")
    monkeypatch.setattr(route, "tenant_policy", lambda db, tenant_id: {})
    monkeypatch.setattr(route, "_system_prompt", lambda *args: "tenant prompt")
    monkeypatch.setattr(route, "OpenRouterTurnService", FakeTurnService)
    return db


@pytest.mark.asyncio
async def test_openrouter_turn_returns_text_for_valid_active_call(monkeypatch):
    db = setup_route(monkeypatch)
    payload = route.OpenRouterTurnPayload(room_token="valid", text=" Hi ", history=[])
    result = await route.openrouter_webcall_turn("call-1", payload)
    assert result == {"text": "Hello from OpenRouter", "provider": "openrouter"}
    assert db.closed


@pytest.mark.asyncio
async def test_openrouter_turn_rejects_invalid_token(monkeypatch):
    setup_route(monkeypatch)
    payload = route.OpenRouterTurnPayload(room_token="invalid", text="Hi", history=[])
    with pytest.raises(HTTPException) as error:
        await route.openrouter_webcall_turn("call-1", payload)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_openrouter_turn_rejects_inactive_call(monkeypatch):
    setup_route(monkeypatch, call_status="completed")
    payload = route.OpenRouterTurnPayload(room_token="valid", text="Hi", history=[])
    with pytest.raises(HTTPException) as error:
        await route.openrouter_webcall_turn("call-1", payload)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_openrouter_end_marks_active_call_completed(monkeypatch):
    db = setup_route(monkeypatch)
    payload = route.OpenRouterTurnPayload(room_token="valid", text="end", history=[])
    result = await route.end_openrouter_webcall("call-1", payload)
    assert result == {"status": "completed"}
    assert db.call.status == "completed"
    assert db.call.ended_at is not None
