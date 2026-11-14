"""AI Voice tenant configuration models.

Provider-neutral configuration for agents, SIP trunks and DID assignments.
Secrets are stored only as encrypted ciphertext and must never be serialized
back to tenant or platform dashboards.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _id() -> str:
    return str(uuid.uuid4())


class VoiceAgentConfig(Base):
    __tablename__ = "voice_agent_configs"
    __table_args__ = (
        Index("ix_voice_agent_configs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    industry_template: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    language_codes_json: Mapped[str] = mapped_column(Text, default='["en","hi","te"]')
    voice_provider: Mapped[str] = mapped_column(String(40), default="platform_default")
    voice_profile: Mapped[str | None] = mapped_column(String(120), nullable=True)
    greeting: Mapped[str] = mapped_column(Text, default="")
    operating_instructions: Mapped[str] = mapped_column(Text, default="")
    knowledge_scope: Mapped[str] = mapped_column(String(30), default="tenant_approved")
    human_handoff_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SipTrunk(Base):
    __tablename__ = "ai_voice_sip_trunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_ai_voice_trunk_tenant_name"),
        Index("ix_ai_voice_sip_trunks_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    # Null tenant_id is reserved for platform-owned trunks managed by Super Admin.
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    registrar_host: Mapped[str] = mapped_column(String(255), nullable=False)
    registrar_port: Mapped[int] = mapped_column(Integer, default=5060)
    transport: Mapped[str] = mapped_column(String(12), default="udp")
    auth_username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Ciphertext only. Encrypt/decrypt through the platform's credential vault helper.
    credentials_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    outbound_proxy: Mapped[str | None] = mapped_column(String(255), nullable=True)
    codecs_json: Mapped[str] = mapped_column(Text, default='["opus","pcmu","pcma"]')
    direction: Mapped[str] = mapped_column(String(20), default="bidirectional")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_health_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DidNumber(Base):
    __tablename__ = "ai_voice_did_numbers"
    __table_args__ = (
        UniqueConstraint("e164_number", name="uq_ai_voice_did_e164"),
        Index("ix_ai_voice_did_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    # Null tenant_id means available in platform inventory, not public/unowned.
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    trunk_id: Mapped[str] = mapped_column(ForeignKey("ai_voice_sip_trunks.id"), nullable=False, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("voice_agent_configs.id"), nullable=True, index=True)
    e164_number: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_number_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    inbound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    outbound_caller_id_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="inventory", index=True)
    provision_state: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
