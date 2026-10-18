"""Persistence models for the AEO/GEO visibility module."""
from datetime import datetime
import uuid
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def _uid():
    return str(uuid.uuid4())

class VisibilityBrand(Base):
    __tablename__ = "visibility_brands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    primary_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    locale: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class VisibilityCompetitor(Base):
    __tablename__ = "visibility_competitors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class VisibilityQuery(Base):
    __tablename__ = "visibility_queries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(String(500), nullable=False)
    intent: Mapped[str] = mapped_column(String(30), default="informational", nullable=False)
    locale: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    topic: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class VisibilityCheckRun(Base):
    __tablename__ = "visibility_check_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    query_id: Mapped[str | None] = mapped_column(ForeignKey("visibility_queries.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    measurement_method: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class VisibilityObservation(Base):
    __tablename__ = "visibility_observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("visibility_check_runs.id"), nullable=False, index=True)
    brand_mentioned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mentioned_names_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    cited_urls_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    answer_excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_quality: Mapped[str] = mapped_column(String(30), default="unverified", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

Index("ix_visibility_queries_tenant_created", VisibilityQuery.tenant_id, VisibilityQuery.created_at)
Index("ix_visibility_runs_tenant_created", VisibilityCheckRun.tenant_id, VisibilityCheckRun.created_at)
