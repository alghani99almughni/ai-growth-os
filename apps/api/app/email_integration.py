"""Email integration: IMAP polling + SMTP sending + AI auto-reply.

Provider presets:
  gmail    -> imap.gmail.com:993,  smtp.gmail.com:587
  outlook  -> outlook.office365.com:993, smtp.office365.com:587
  custom   -> caller supplies host/port for both

All credentials are stored encrypted in TenantEmailAccount.config_encrypted
using INTEGRATION_CREDENTIAL_ENCRYPTION_KEY (same key as WhatsApp/Meta).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from imap_tools import MailBox, AND

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .integrations import encrypt_channel_config, decrypt_channel_config
from .models_email import TenantEmailAccount, EmailLog

logger = logging.getLogger("api.email")

PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "gmail": {
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_starttls": True,
    },
    "outlook": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_starttls": True,
    },
    "custom": {},
}


def _encryption_key() -> str:
    key = settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key
    if not key:
        raise RuntimeError("No encryption key configured for integration credentials")
    return key


def encrypt_email_config(cfg: dict) -> str:
    return encrypt_channel_config(cfg, _encryption_key())


def decrypt_email_config(encrypted: str) -> dict:
    return decrypt_channel_config(encrypted, _encryption_key())


def build_config_from_input(provider: str, data: dict) -> dict:
    """Merge caller-supplied data with the preset defaults."""
    preset = dict(PROVIDER_PRESETS.get(provider, {}))
    for k in (
        "imap_host", "imap_port", "imap_user", "imap_password",
        "smtp_host", "smtp_port", "smtp_user", "smtp_password",
    ):
        if data.get(k) is not None:
            preset[k] = data[k]
    if "imap_user" not in preset or not preset["imap_user"]:
        preset["imap_user"] = data.get("email_address", "")
    if "smtp_user" not in preset or not preset["smtp_user"]:
        preset["smtp_user"] = preset.get("imap_user", "")
    if not preset.get("imap_password") and preset.get("smtp_password"):
        preset["imap_password"] = preset["smtp_password"]
    if not preset.get("smtp_password") and preset.get("imap_password"):
        preset["smtp_password"] = preset["imap_password"]
    preset["smtp_starttls"] = preset.get("smtp_starttls", True)
    return preset


def test_connection_sync(cfg: dict) -> dict:
    """Try to open an IMAP connection. Returns {ok, error?}."""
    try:
        with MailBox(cfg["imap_host"], port=int(cfg["imap_port"])).login(
            cfg["imap_user"], cfg["imap_password"], initial_folder="INBOX"
        ) as mb:
            # Probe the inbox with a cheap header-only fetch to prove the
            # connection is live. imap_tools 1.15 does not expose folder_list().
            _ = next(iter(mb.fetch(limit=1, headers_only=True)), None)
            return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fetch_new_messages_sync(cfg: dict, limit: int = 20) -> list[dict]:
    """Fetch unread messages from INBOX. Marks them as seen."""
    out: list[dict] = []
    with MailBox(cfg["imap_host"], port=int(cfg["imap_port"])).login(
        cfg["imap_user"], cfg["imap_password"], initial_folder="INBOX"
    ) as mb:
        for msg in mb.fetch(AND(seen=False), limit=limit, mark_seen=True, reverse=True):
            text = msg.text or msg.html or ""
            out.append({
                "uid": msg.uid,
                "message_id": (msg.headers.get("message-id") or [""])[0],
                "from": msg.from_,
                "to": ", ".join(msg.to or []),
                "subject": msg.subject or "",
                "text": text.strip(),
                "date": msg.date.isoformat() if msg.date else None,
            })
    return out


async def send_reply_smtp(cfg: dict, to_address: str, subject: str, body: str) -> None:
    """Send a plain-text reply over SMTP."""
    msg = EmailMessage()
    msg["From"] = cfg["smtp_user"]
    msg["To"] = to_address
    msg["Subject"] = "Re: " + subject if not subject.lower().startswith("re:") else subject
    msg.set_content(body)

    await aiosmtplib.send(
        msg,
        hostname=cfg["smtp_host"],
        port=int(cfg["smtp_port"]),
        username=cfg["smtp_user"],
        password=cfg["smtp_password"],
        start_tls=bool(cfg.get("smtp_starttls", True)),
    )


# ---------- Account CRUD helpers (used by main.py endpoints) ----------

def list_accounts(db: Session, tenant_id: str) -> list[dict]:
    rows = db.scalars(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id)
        .order_by(TenantEmailAccount.created_at.desc())
    ).all()
    return [_account_out(r) for r in rows]


def _account_out(r: TenantEmailAccount) -> dict:
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "label": r.label,
        "provider": r.provider,
        "email_address": r.email_address,
        "role": r.role,
        "is_active": r.is_active,
        "auto_reply_enabled": r.auto_reply_enabled,
        "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
        "last_error": r.last_error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def create_account(
    db: Session,
    tenant_id: str,
    *,
    label: str,
    provider: str,
    email_address: str,
    role: str,
    cfg: dict,
) -> dict:
    encrypted = encrypt_email_config(cfg)
    row = TenantEmailAccount(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        label=label,
        provider=provider,
        email_address=email_address,
        role=role,
        config_encrypted=encrypted,
        is_active=True,
        auto_reply_enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _account_out(row)


def delete_account(db: Session, tenant_id: str, account_id: str) -> bool:
    row = db.scalar(
        select(TenantEmailAccount).where(
            TenantEmailAccount.id == account_id,
            TenantEmailAccount.tenant_id == tenant_id,
        )
    )
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def list_log(db: Session, tenant_id: str, limit: int = 100) -> list[dict]:
    rows = db.scalars(
        select(EmailLog)
        .where(EmailLog.tenant_id == tenant_id)
        .order_by(EmailLog.created_at.desc())
        .limit(min(max(limit, 1), 500))
    ).all()
    return [{
        "id": r.id,
        "account_id": r.account_id,
        "from_address": r.from_address,
        "to_address": r.to_address,
        "subject": r.subject,
        "outcome": r.outcome,
        "reply_text": r.reply_text,
        "error": r.error,
        "ticket_id": r.ticket_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]