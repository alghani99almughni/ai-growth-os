import asyncio
import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Tenant
from app.models_growth import MenuItem, Order, VoiceOrderDraft
import app.voice_order_actions as actions


def _db():
    import app.models_ai  # noqa: F401
    import app.models_growth  # noqa: F401
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id="tenant-a", name="Cafe", slug="cafe", industry="restaurant")
    db.add(tenant)
    db.add(MenuItem(id="dosa", tenant_id="tenant-a", name="Dosa", price=80,
                    is_active=True, is_available=True))
    db.commit()
    return db, tenant


def test_voice_order_requires_explicit_confirmation_and_commits_once(monkeypatch):
    db, tenant = _db()
    monkeypatch.setattr(actions, "_feature_enabled", lambda *_: True)
    context = {"conversation_id": "conv-1", "customer": None, "channel": "webrtc"}
    draft_reply = asyncio.run(actions.handle_voice_order(
        db, tenant, "I want 2 Dosa", "en", {}, context
    ))
    assert "₹160" in draft_reply and "Shall I place" in draft_reply
    assert db.query(Order).count() == 0
    assert db.query(VoiceOrderDraft).one().status == "awaiting_confirmation"

    confirmed = asyncio.run(actions.handle_voice_order(
        db, tenant, "Yes, confirm", "en", {}, context
    ))
    assert "Confirmed" in confirmed
    assert db.query(Order).count() == 1
    assert db.query(VoiceOrderDraft).one().status == "committed"

    # A repeated affirmative cannot create a second order.
    asyncio.run(actions.handle_voice_order(db, tenant, "Yes", "en", {}, context))
    assert db.query(Order).count() == 1
    db.close()


def test_voice_order_cancel_discards_draft(monkeypatch):
    db, tenant = _db()
    monkeypatch.setattr(actions, "_feature_enabled", lambda *_: True)
    context = {"conversation_id": "conv-2", "customer": None}
    asyncio.run(actions.handle_voice_order(db, tenant, "I want Dosa", "en", {}, context))
    reply = asyncio.run(actions.handle_voice_order(db, tenant, "No, cancel", "en", {}, context))
    assert "cancelled" in reply.lower()
    assert db.query(Order).count() == 0
    assert db.query(VoiceOrderDraft).one().status == "cancelled"
    db.close()


def test_voice_order_revalidates_price_before_confirmation(monkeypatch):
    db, tenant = _db()
    monkeypatch.setattr(actions, "_feature_enabled", lambda *_: True)
    context = {"conversation_id": "conv-3", "customer": None}
    asyncio.run(actions.handle_voice_order(db, tenant, "I want 2 Dosa", "en", {}, context))
    db.query(MenuItem).filter_by(id="dosa").one().price = 90
    db.commit()
    reply = asyncio.run(actions.handle_voice_order(db, tenant, "Yes", "en", {}, context))
    assert "price has changed" in reply.lower()
    assert db.query(Order).count() == 0
    db.close()


def test_voice_order_does_not_match_other_tenant_menu(monkeypatch):
    db, tenant = _db()
    other = Tenant(id="tenant-b", name="Other", slug="other", industry="restaurant")
    db.add(other)
    db.add(MenuItem(id="other-dosa", tenant_id="tenant-b", name="Dosa Special",
                    price=100, is_active=True, is_available=True))
    db.commit()
    monkeypatch.setattr(actions, "_feature_enabled", lambda *_: True)
    context = {"conversation_id": "conv-4", "customer": None}
    reply = asyncio.run(actions.handle_voice_order(
        db, tenant, "I want Dosa Special", "en", {}, context
    ))
    assert "exact item name" in reply.lower()
    assert db.query(VoiceOrderDraft).count() == 0
    db.close()
