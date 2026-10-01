"""Call capture models.

Every AI call produces:
    - one CallRecording (whole-call metadata)
    - one CallTurn per exchange (customer + AI audio + text + state)
    - zero or more CallFlags (auto-detected errors)

Audio files live on disk (dev) or S3/R2 (prod). Metadata is fully relational
so dashboards can query and join.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
import uuid


def uid():
    return str(uuid.uuid4())


class CallRecording(Base):
    __tablename__ = "call_recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    call_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    customer_name: Mapped[str] = mapped_column(String(160), default="Guest")
    customer_phone: Mapped[str] = mapped_column(String(32), default="")

    channel: Mapped[str] = mapped_column(String(30), default="webrtc")
    language_start: Mapped[str] = mapped_column(String(16), default="en")
    language_end: Mapped[str] = mapped_column(String(16), default="en")

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(30), default="in_progress", index=True)
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    intent_final: Mapped[str | None] = mapped_column(String(120), nullable=True)

    has_flags: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    flag_count: Mapped[int] = mapped_column(Integer, default=0)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)

    avg_turn_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_customer_audio_bytes: Mapped[int] = mapped_column(Integer, default=0)
    total_ai_audio_bytes: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CallTurn(Base):
    __tablename__ = "call_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("call_recordings.id"), index=True)

    turn_number: Mapped[int] = mapped_column(Integer, default=1)
    ts_started: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ts_ended: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Customer side
    customer_text: Mapped[str] = mapped_column(Text, default="")
    customer_audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_audio_ms: Mapped[int] = mapped_column(Integer, default=0)
    stt_latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Classifier output
    intent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    language: Mapped[str] = mapped_column(String(16), default="en")
    entities_json: Mapped[str] = mapped_column(Text, default="{}")

    # Handler / orchestrator
    source: Mapped[str] = mapped_column(String(30), default="handler")
    handler_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    handler_succeeded: Mapped[bool] = mapped_column(Boolean, default=False)
    state_before: Mapped[str | None] = mapped_column(String(60), nullable=True)
    state_after: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cleared_at_set: Mapped[bool] = mapped_column(Boolean, default=False)

    # AI side
    ai_text: Mapped[str] = mapped_column(Text, default="")
    ai_audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_audio_ms: Mapped[int] = mapped_column(Integer, default=0)
    tts_latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Overall
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CallFlag(Base):
    __tablename__ = "call_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("call_recordings.id"), index=True)
    turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    flag_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)