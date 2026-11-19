import asyncio
import json
from types import SimpleNamespace

from app.main import _notify_voice_callback


class _FakeDb:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1


def test_voice_callback_notifies_configured_tenant_contacts(monkeypatch):
    import app.notifications as notifications

    async def fake_email(to, subject, message):
        assert to == "owner@example.com"
        return {"sent": True, "status": "sent", "channel": "email"}

    async def fake_whatsapp(to, message):
        assert to == "+919876543210"
        return {"sent": True, "status": "sent", "channel": "whatsapp"}

    monkeypatch.setattr(notifications, "send_email", fake_email)
    monkeypatch.setattr(notifications, "send_platform_whatsapp", fake_whatsapp)

    tenant = SimpleNamespace(id="tenant-a", name="Clinic A", email="owner@example.com",
                             whatsapp_number="+919876543210")
    call = SimpleNamespace(id="call-a", customer_id="customer-a")
    request = SimpleNamespace(id="request-a", message="Please call the customer back.")
    db = _FakeDb()

    result = asyncio.run(_notify_voice_callback(db, tenant, call, request))

    assert result["email"]["sent"] is True
    assert result["whatsapp"]["sent"] is True
    assert db.commits == 1
    assert len(db.added) == 1
    event = db.added[0]
    assert event.tenant_id == "tenant-a"
    assert event.call_id == "call-a"
    assert event.event_type == "callback_notification"
    payload = json.loads(event.payload_json)
    assert payload["request_id"] == "request-a"
    assert payload["email"]["status"] == "sent"
    assert payload["whatsapp"]["status"] == "sent"


def test_voice_callback_records_missing_notification_destinations(monkeypatch):
    import app.notifications as notifications

    async def unexpected(*args, **kwargs):
        raise AssertionError("A provider must not be called without a tenant destination.")

    monkeypatch.setattr(notifications, "send_email", unexpected)
    monkeypatch.setattr(notifications, "send_platform_whatsapp", unexpected)

    tenant = SimpleNamespace(id="tenant-b", name="Business B", email=None, whatsapp_number=None)
    call = SimpleNamespace(id="call-b", customer_id=None)
    request = SimpleNamespace(id="request-b", message="Callback requested.")
    db = _FakeDb()

    result = asyncio.run(_notify_voice_callback(db, tenant, call, request))

    assert result["email"]["status"] == "no_tenant_email"
    assert result["whatsapp"]["status"] == "no_tenant_whatsapp"
    payload = json.loads(db.added[0].payload_json)
    assert payload["email"]["sent"] is False
    assert payload["whatsapp"]["sent"] is False
