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


def test_smtp_connection_sync(cfg: dict) -> dict:
    """Verify SMTP TLS/authentication without sending an email."""
    import smtplib
    import ssl

    host = str(cfg.get("smtp_host") or "").strip()
    user = str(cfg.get("smtp_user") or "").strip()
    password = str(cfg.get("smtp_password") or "")
    port = int(cfg.get("smtp_port") or 0)
    if not host or not user or not password or not port:
        return {"ok": False, "error": "SMTP host, port, username and password are required"}

    use_tls = bool(cfg.get("smtp_use_tls", False) or port == 465)
    try:
        if use_tls:
            with smtplib.SMTP_SSL(host, port, timeout=12, context=ssl.create_default_context()) as smtp:
                smtp.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=12) as smtp:
                smtp.ehlo()
                if bool(cfg.get("smtp_starttls", True)):
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(user, password)
        return {"ok": True}
    except Exception as exc:
        # Never include the password in diagnostics.
        return {"ok": False, "error": str(exc)[:240]}


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
                "in_reply_to": (msg.headers.get("in-reply-to") or [""])[0],
                "references": " ".join(msg.headers.get("references") or []),
                "from": msg.from_,
                "to": ", ".join(msg.to or []),
                "subject": msg.subject or "",
                "text": text.strip(),
                "date": msg.date.isoformat() if msg.date else None,
            })
    return out


async def send_reply_smtp(
    cfg: dict,
    to_address: str,
    subject: str,
    body: str,
    *,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> str:
    """Send a plain-text reply and return its outbound Message-ID."""
    msg = EmailMessage()
    msg["From"] = cfg["smtp_user"]
    msg["To"] = to_address
    sender_domain = cfg["smtp_user"].rsplit("@", 1)[-1] if "@" in cfg["smtp_user"] else "localhost"
    msg["Message-ID"] = f"<{uuid.uuid4()}@{sender_domain}>"
    clean_subject = (subject or "").strip()
    msg["Subject"] = clean_subject if clean_subject.lower().startswith("re:") else "Re: " + clean_subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to.strip()
        chain = " ".join(x for x in ((references or "").strip(), in_reply_to.strip()) if x)
        if chain:
            msg["References"] = chain
    elif references:
        msg["References"] = references.strip()
    msg.set_content(body)

    await aiosmtplib.send(
        msg,
        hostname=cfg["smtp_host"],
        port=int(cfg["smtp_port"]),
        username=cfg["smtp_user"],
        password=cfg["smtp_password"],
        use_tls=bool(cfg.get("smtp_use_tls", False) or int(cfg.get("smtp_port", 0)) == 465),
        start_tls=bool(cfg.get("smtp_starttls", True) and not (cfg.get("smtp_use_tls", False) or int(cfg.get("smtp_port", 0)) == 465)),
    )
    return str(msg["Message-ID"])


async def send_email_smtp(cfg: dict, to_address: str, subject: str, body: str) -> str:
    """Send a new outbound email using a tenant mailbox's encrypted SMTP config."""
    msg = EmailMessage()
    msg["From"] = cfg["smtp_user"]
    msg["To"] = to_address
    msg["Subject"] = (subject or "").strip() or "Message from the business"
    sender_domain = cfg["smtp_user"].rsplit("@", 1)[-1] if "@" in cfg["smtp_user"] else "localhost"
    msg["Message-ID"] = f"<{uuid.uuid4()}@{sender_domain}>"
    msg.set_content(body)
    await aiosmtplib.send(
        msg,
        hostname=cfg["smtp_host"],
        port=int(cfg["smtp_port"]),
        username=cfg["smtp_user"],
        password=cfg["smtp_password"],
        use_tls=bool(cfg.get("smtp_use_tls", False) or int(cfg.get("smtp_port", 0)) == 465),
        start_tls=bool(cfg.get("smtp_starttls", True) and not (cfg.get("smtp_use_tls", False) or int(cfg.get("smtp_port", 0)) == 465)),
    )
    return str(msg["Message-ID"])


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
def list_threads(db: Session, tenant_id: str, limit: int = 100) -> list[dict]:
    from .email_threading import group_threads
    from sqlalchemy import select as _select
    rows = db.scalars(
        _select(EmailLog)
        .where(EmailLog.tenant_id == tenant_id)
        .order_by(EmailLog.created_at.desc())
        .limit(max(1, min(limit * 5, 1000)))
    ).all()
    threads = group_threads(rows)
    return threads[:limit]


def list_thread_messages(db: Session, tenant_id: str, thread_id: str) -> dict | None:
    from .email_threading import group_threads
    from sqlalchemy import select as _select
    rows = db.scalars(
        _select(EmailLog).where(EmailLog.tenant_id == tenant_id)
    ).all()
    for t in group_threads(rows):
        if t["thread_id"] == thread_id:
            return t
    return None