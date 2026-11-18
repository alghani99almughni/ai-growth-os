"""Persistence guarantees for the standalone AI Voice call recorder."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Tenant
from app.models_calls import CallRecording, CallTurn
from app.call_recorder import CallRecorder


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_customer_transcript_is_committed_before_ai_reply():
    db = make_session()
    db.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a", industry="services"))
    db.commit()

    recorder = CallRecorder(db, "tenant-a", customer_name="Caller")
    recording_id = recorder.start()
    assert recording_id

    recorder.begin_turn()
    recorder.capture_customer("I need an appointment")

    # Simulate the orchestrator failing before it can produce an AI response.
    turn = db.scalar(select(CallTurn).where(CallTurn.recording_id == recording_id))
    assert turn is not None
    assert turn.customer_text == "I need an appointment"
    assert turn.ai_text == ""

    recorder.finish(status="failed", outcome="orchestration_error")
    db.expire_all()
    saved = db.get(CallRecording, recording_id)
    assert saved.status == "failed"
    assert saved.turn_count == 1
    db.close()


def test_ai_text_updates_same_turn_and_survives_missing_audio(monkeypatch):
    db = make_session()
    db.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a", industry="services"))
    db.commit()

    def audio_failure(*args, **kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr("app.call_storage.save_audio", audio_failure, raising=False)
    recorder = CallRecorder(db, "tenant-a")
    recording_id = recorder.start()
    assert recording_id

    recorder.begin_turn()
    recorder.capture_customer("Hello", audio_bytes=b"customer-audio")
    recorder.capture_ai("How can I help?", audio_bytes=b"assistant-audio")

    turns = db.scalars(select(CallTurn).where(CallTurn.recording_id == recording_id)).all()
    assert len(turns) == 1
    assert turns[0].customer_text == "Hello"
    assert turns[0].ai_text == "How can I help?"
    assert turns[0].customer_audio_url is None
    assert turns[0].ai_audio_url is None
    recorder.finish()
    db.close()


def test_greeting_without_customer_utterance_is_recorded():
    db = make_session()
    db.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a", industry="services"))
    db.commit()

    recorder = CallRecorder(db, "tenant-a")
    recording_id = recorder.start()
    assert recording_id
    recorder.begin_turn()
    recorder.capture_ai("Welcome")

    turn = db.scalar(select(CallTurn).where(CallTurn.recording_id == recording_id))
    assert turn is not None
    assert turn.customer_text == ""
    assert turn.ai_text == "Welcome"
    db.close()



def test_call_links_only_to_customer_in_same_tenant():
    db = make_session()
    db.add_all([
        Tenant(id="tenant-a", name="Tenant A", slug="tenant-a", industry="services"),
        Tenant(id="tenant-b", name="Tenant B", slug="tenant-b", industry="services"),
    ])
    from app.models import Customer
    db.add_all([
        Customer(id="customer-a", tenant_id="tenant-a", name="Verified Caller", phone="+919876543210"),
        Customer(id="customer-b", tenant_id="tenant-b", name="Other Tenant Caller", phone="+919876543211"),
    ])
    db.commit()

    valid = CallRecorder(db, "tenant-a", customer_id="customer-a", customer_name="Guest")
    valid_id = valid.start()
    assert valid_id
    valid_recording = db.get(CallRecording, valid_id)
    assert valid_recording.customer_id == "customer-a"
    assert valid_recording.customer_name == "Verified Caller"
    assert valid_recording.customer_phone == "+919876543210"

    cross_tenant = CallRecorder(db, "tenant-a", customer_id="customer-b")
    cross_id = cross_tenant.start()
    assert cross_id
    cross_recording = db.get(CallRecording, cross_id)
    assert cross_recording.customer_id is None
    db.close()
