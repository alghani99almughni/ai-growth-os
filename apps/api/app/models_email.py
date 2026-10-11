"""Email accounts and auto-reply log for tenant mailboxes.

Each tenant can register one or more mailboxes (contact@, support@,
billing@). A background poller reads incoming mail over IMAP, generates
an AI reply using the tenant's own AI provider key, and sends it back
over SMTP.

Provider presets cover Gmail / Outlook / any custom SMTP server.
Credentials are encrypted at rest with INTEGRATION_CREDENTIAL_ENCRYPTION_KEY.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text

from .db import Base


class TenantEmailAccount(Base):
    __tablename__ = "tenant_email_accounts"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    label = Column(String, nullable=False, default="Primary mailbox")

    # "gmail" | "outlook" | "custom"
    provider = Column(String, nullable=False, default="custom")

    # The visible email address (contact@business.com etc.)
    email_address = Column(String, nullable=False)

    # Encrypted JSON containing:
    #   imap_host, imap_port, imap_user, imap_password,
    #   smtp_host, smtp_port, smtp_user, smtp_password
    config_encrypted = Column(Text, nullable=False)

    # Which role this mailbox serves: "contact" | "support" | "billing" | "general"
    role = Column(String, nullable=False, default="general")

    is_active = Column(Boolean, nullable=False, default=True)
    auto_reply_enabled = Column(Boolean, nullable=False, default=True)

    last_checked_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailLog(Base):
    """One row per incoming email that was processed."""
    __tablename__ = "email_logs"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)

    # Message-Id header from the original email (used for de-duplication)
    message_id = Column(String, nullable=False, index=True)

    from_address = Column(String, nullable=False)
    to_address = Column(String, nullable=False)
    subject = Column(String, nullable=False, default="")

    # "replied" | "skipped" | "failed" | "ticket_created"
    outcome = Column(String, nullable=False, default="replied")

    reply_text = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    ticket_id = Column(String, nullable=True, index=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

class PlatformEmailMessage(Base):
    """Persisted messages received by the platform-owned Super Admin mailbox."""
    __tablename__ = "platform_email_messages"

    id = Column(String, primary_key=True)
    message_id = Column(String, nullable=False, unique=True, index=True)
    from_address = Column(String, nullable=False)
    to_address = Column(String, nullable=False, default="")
    subject = Column(String, nullable=False, default="")
    body = Column(Text, nullable=False, default="")
    received_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    reply_text = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="unread", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PlatformWhatsAppMessage(Base):
    """Inbound/outbound conversation history for the platform-owned WhatsApp line."""
    __tablename__ = "platform_whatsapp_messages"

    id = Column(String, primary_key=True)
    provider_message_id = Column(String, nullable=True, unique=True, index=True)
    phone = Column(String, nullable=False, index=True)
    contact_name = Column(String, nullable=True)
    body = Column(Text, nullable=False, default="")
    direction = Column(String, nullable=False, default="inbound", index=True)
    status = Column(String, nullable=False, default="received", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PlatformContactPreference(Base):
    """Platform-wide communication opt-outs for tenant and prospect contacts."""
    __tablename__ = "platform_contact_preferences"

    id = Column(String, primary_key=True)
    phone_norm = Column(String, nullable=True, unique=True, index=True)
    email_norm = Column(String, nullable=True, unique=True, index=True)
    whatsapp_opt_out = Column(Boolean, nullable=False, default=False)
    email_opt_out = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
