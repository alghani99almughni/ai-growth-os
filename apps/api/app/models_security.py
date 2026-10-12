"""Tenant-scoped security and visitor management entities."""
from datetime import datetime
import uuid
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def _uid(): return str(uuid.uuid4())

class SecuritySite(Base):
    __tablename__ = "security_sites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    industry: Mapped[str] = mapped_column(String(40), default="apartment")
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class VisitorPass(Base):
    __tablename__ = "security_visitor_passes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("security_sites.id"), nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    visitor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    visitor_mobile: Mapped[str] = mapped_column(String(32), default="")
    purpose: Mapped[str] = mapped_column(String(240), default="")
    destination: Mapped[str] = mapped_column(String(240), default="")
    vehicle_number: Mapped[str] = mapped_column(String(40), default="")
    industry: Mapped[str] = mapped_column(String(40), default="apartment")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    snapshot_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index("ix_security_pass_tenant_created", "tenant_id", "created_at"),)

class VisitorEvent(Base):
    __tablename__ = "security_visitor_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    pass_id: Mapped[str] = mapped_column(ForeignKey("security_visitor_passes.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
