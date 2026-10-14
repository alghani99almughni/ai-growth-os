"""Persistent platform-owned inbox templates and automation settings."""
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text
from .db import Base

class PlatformReplyTemplate(Base):
    __tablename__ = "platform_reply_templates"
    id = Column(String, primary_key=True)
    channel = Column(String, nullable=False, index=True)  # email | whatsapp
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False, default="")
    body = Column(Text, nullable=False)
    keywords = Column(Text, nullable=False, default="")  # comma-separated, empty means fallback only
    is_active = Column(Boolean, nullable=False, default=True)
    auto_reply = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
