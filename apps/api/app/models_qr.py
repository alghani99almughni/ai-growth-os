"""QR architecture models (blueprint Section 8).

Three QR kinds:
    business  -> opens the full PWA
    context   -> PWA + opaque context token (table/room/seat/counter/product/property)
    campaign  -> PWA + attribution (which flyer/ad/offer)

Pattern: app.example.com/c/<opaque-token>

Scans are recorded per-QR with timestamp, optional customer, and source
metadata. This model is additive — it does NOT replace QrEntry, it
extends the QrEntry table with new nullable columns via migration.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
import uuid


def uid():
    return str(uuid.uuid4())


class QrScan(Base):
    """One row per QR scan. Append-only. Never updated."""
    __tablename__ = "qr_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    qr_id: Mapped[str] = mapped_column(String(36), index=True)
    token: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    context_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    context_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)