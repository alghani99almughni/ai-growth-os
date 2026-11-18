from datetime import date, datetime
from types import SimpleNamespace

import app.voice_booking_actions as actions
from app.voice_booking_actions import _action_intent, _affirmative, _negative, _parse_new_start


def test_detects_cancellation_request():
    assert _action_intent("Please cancel my appointment") == "cancel"


def test_detects_rescheduling_request():
    assert _action_intent("Can you reschedule my appointment to Monday?") == "reschedule"
    assert _action_intent("Change my appointment time") == "reschedule"


def test_does_not_treat_unrelated_message_as_appointment_action():
    assert _action_intent("What are your opening hours?") is None


def test_explicit_confirmation_is_narrow():
    assert _affirmative("Yes, please")
    assert _affirmative("हाँ")
    assert not _affirmative("yes, but maybe later")
    assert _negative("No thanks")
    assert not _negative("No, actually yes")

def test_recognizes_natural_reschedule_phrasing():
    assert _action_intent("Can I change the timing of my appointment?") == "reschedule"
    assert _action_intent("Move it to Monday at 11 AM") == "reschedule"

def test_reschedule_parser_requires_explicit_am_pm(monkeypatch):
    monkeypatch.setattr(actions, "extract_booking_entities", lambda text: {
        "day": "Monday", "relative_day": None, "date_hint": None, "time": "11:00"
    })
    monkeypatch.setattr(actions, "resolve_booking_date", lambda tenant, day, relative, hint, **kwargs: date(2026, 10, 12))
    monkeypatch.setattr(actions, "resolve_voice_time", lambda *args: {"status": "clarification_required", "candidates": []})
    tenant = SimpleNamespace(id="t1", timezone="Asia/Kolkata")
    call = SimpleNamespace(started_at=datetime(2026, 10, 10, 4, 0), transcript="")
    db = SimpleNamespace(scalar=lambda query: None)
    result = _parse_new_start(db, tenant, call, "Monday at 11")
    assert result["status"] == "clarification_required"


def test_reschedule_parser_converts_explicit_time(monkeypatch):
    monkeypatch.setattr(actions, "extract_booking_entities", lambda text: {
        "day": "Monday", "relative_day": None, "date_hint": None, "time": "11:00 AM"
    })
    monkeypatch.setattr(actions, "resolve_booking_date", lambda tenant, day, relative, hint, **kwargs: date(2026, 10, 12))
    monkeypatch.setattr(actions, "resolve_voice_time", lambda *args: {"status": "resolved", "time": __import__("datetime").time(11, 0)})
    tenant = SimpleNamespace(id="t1", timezone="Asia/Kolkata")
    call = SimpleNamespace(started_at=datetime(2026, 10, 10, 4, 0), transcript="")
    db = SimpleNamespace(scalar=lambda query: None)
    result = _parse_new_start(db, tenant, call, "Monday at 11 AM")
    assert result == {"status": "resolved", "starts_at": datetime(2026, 10, 12, 11, 0)}



def test_voice_appointment_action_rejects_cross_tenant_call_customer():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import Tenant, Customer
    from app.models_growth import CallRecord
    from app.voice_booking_actions import handle_voice_appointment_action

    # Import model modules so all referenced tables are registered.
    import app.models_ai  # noqa: F401
    import app.models_growth  # noqa: F401
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant_a = Tenant(id="tenant-a", name="Tenant A", slug="tenant-a", industry="services")
    tenant_b = Tenant(id="tenant-b", name="Tenant B", slug="tenant-b", industry="services")
    customer_b = Customer(id="customer-b", tenant_id="tenant-b", name="Other tenant", phone="+919999999999")
    db.add_all([tenant_a, tenant_b, customer_b])
    db.commit()
    call = CallRecord(id="call-a", tenant_id="tenant-a", customer_id="customer-b",
                      started_at=datetime(2026, 11, 18, 8, 0), transcript="")
    db.add(call)
    db.commit()

    result = handle_voice_appointment_action(
        db, tenant_a, call, None, "Please cancel my appointment", ""
    )
    assert result["appointment_action"]["status"] == "identity_error"
    assert db.query(Customer).filter_by(id="customer-b").one().tenant_id == "tenant-b"
    db.close()
