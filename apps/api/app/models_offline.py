"""Offline call models.

When a WebRTC call drops and the browser captured audio + identity locally,
the device pushes a payload to /offline-call when the internet returns.
Each payload lands here for processing.

Rows move through states:
    received -> transcribing -> processed (or failed)

Audio lives on disk/S3, referenced by URL. Everything else is relational.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
import uuid


def uid():
    return str(uuid.uuid4())


class OfflineCall(Base):
    __tablename__ = "offline_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)

    customer_name: Mapped[str] = mapped_column(String(160), default="Guest")
    customer_phone: Mapped[str] = mapped_column(String(32), default="")
    customer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    channel: Mapped[str] = mapped_column(String(30), default="widget_offline")
    language: Mapped[str] = mapped_column(String(16), default="en")
    call_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    audio_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)

    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    language_detected: Mapped[str | None] = mapped_column(String(16), nullable=True)

    whatsapp_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    email_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="received", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
