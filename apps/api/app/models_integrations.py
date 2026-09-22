from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
import uuid

def uid():
    return str(uuid.uuid4())

class TenantIntegration(Base):
    __tablename__ = "tenant_integrations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    integration_key: Mapped[str] = mapped_column(String(60), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    mode: Mapped[str] = mapped_column(String(20), default="platform")
    status: Mapped[str] = mapped_column(String(30), default="disconnected")
    config_encrypted: Mapped[str] = mapped_column(Text, default="")
    account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PlatformAIProvider(Base):
    __tablename__ = "platform_ai_providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    provider: Mapped[str] = mapped_column(String(60), index=True)
    model: Mapped[str] = mapped_column(String(120))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_encrypted: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="healthy")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
