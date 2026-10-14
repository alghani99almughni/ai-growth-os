"""Tenant-scoped visitor lifecycle records."""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _uid() -> str:
    return str(uuid.uuid4())


class VisitorRecord(Base):
    __tablename__ = "visitor_records"
    __table_args__ = (
        Index("ix_visitor_records_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_visitor_records_tenant_phone", "tenant_id", "phone"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(160), nullable=True)
    purpose: Mapped[str] = mapped_column(String(240), nullable=False)
    host_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    host_staff_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expected_checkout: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    pass_token: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True, default=lambda: __import__("secrets").token_urlsafe(24))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
