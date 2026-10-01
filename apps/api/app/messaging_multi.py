"""Multi-channel messaging.

Unified interface for sending messages via WhatsApp, SMS, and Email.
Each channel is best-effort: failures never raise, they return (success, error).

Uses the tenant's configured integration if available, otherwise the
platform's own provider.

Channels:
    - WhatsApp (via OpenWA or Meta Cloud API, through .integrations)
    - SMS (via a platform provider like Twilio or a tenant-configurable one)
    - Email (via SMTP, through .notifications)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

def send_whatsapp(db, tenant, phone: str, message: str) -> tuple:
    """Send a WhatsApp message to the given phone number.

    Returns (ok: bool, error: Optional[str]).
    """
    if not phone:
        return False, "no_phone"

    try:
        from .integrations import tenant_whatsapp_adapter
        adapter = tenant_whatsapp_adapter(db, tenant.id)
    except Exception as exc:
        logger.debug("whatsapp adapter lookup failed: %s", exc)
        return False, "adapter_unavailable"

    if adapter is None:
        return False, "no_adapter"

    try:
        adapter.send_text(to=phone, body=message)
        return True, None
    except Exception as exc:
        logger.debug("whatsapp send failed: %s", exc)
        return False, str(exc)[:200]


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

def send_sms(db, tenant, phone: str, message: str) -> tuple:
    """Send an SMS. Uses tenant integration if available, else platform.

    Returns (ok: bool, error: Optional[str]).
    """
    if not phone:
        return False, "no_phone"

    # Try tenant integration first.
    try:
        from .models_integrations import TenantIntegration
        from sqlalchemy import select
        row = db.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant.id,
                TenantIntegration.integration_key == "sms",
                TenantIntegration.status == "connected",
            ).limit(1)
        )
        if row is not None:
            ok, err = _send_sms_via_tenant(row, phone, message)
            if ok:
                return True, None
            logger.debug("tenant SMS failed: %s", err)
    except Exception as exc:
        logger.debug("tenant SMS lookup failed: %s", exc)

    # Fall back to platform SMS if configured.
    return _send_sms_via_platform(phone, message)


def _send_sms_via_tenant(integration_row, phone, message):
    try:
        from .integrations import decrypt_channel_config
        cfg = decrypt_channel_config(integration_row)
        provider = (cfg.get("provider") or "").lower()
        if provider == "twilio":
            return _send_via_twilio(cfg, phone, message)
        return False, "unsupported_provider"
    except Exception as exc:
        return False, str(exc)[:200]


def _send_sms_via_platform(phone, message):
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    if not (sid and token and from_number):
        return False, "platform_sms_not_configured"
    cfg = {"account_sid": sid, "auth_token": token, "from_number": from_number}
    return _send_via_twilio(cfg, phone, message)


def _send_via_twilio(cfg, phone, message):
    try:
        from twilio.rest import Client
    except Exception:
        return False, "twilio_sdk_missing"
    try:
        client = Client(cfg["account_sid"], cfg["auth_token"])
        client.messages.create(
            body=message[:1600],
            from_=cfg["from_number"],
            to=phone,
        )
        return True, None
    except Exception as exc:
        logger.debug("twilio send failed: %s", exc)
        return False, str(exc)[:200]


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_email(db, tenant, to_email: str, subject: str, body: str) -> tuple:
    """Send an email via the tenant's SMTP or the platform's.

    Returns (ok: bool, error: Optional[str]).
    """
    if not to_email:
        return False, "no_email"

    try:
        import smtplib
        from email.mime.text import MIMEText

        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", "465"))
        user = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASS")
        if not (host and user and password):
            return False, "smtp_not_configured"

        msg = MIMEText(body or "")
        msg["Subject"] = subject or ""
        msg["From"] = user
        msg["To"] = to_email

        with smtplib.SMTP_SSL(host, port, timeout=10) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        return True, None
    except Exception as exc:
        logger.debug("email send failed: %s", exc)
        return False, str(exc)[:200]


# ---------------------------------------------------------------------------
# Orchestrator: try every channel in priority order
# ---------------------------------------------------------------------------

def notify_customer(
    db,
    tenant,
    *,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    subject: str = "Message from the team",
    body_text: str = "",
    prefer: str = "whatsapp",
) -> dict:
    """Attempt to reach the customer through their preferred channel, then fallback.

    Returns a dict describing what worked:
        {
            "whatsapp": {"ok": True/False, "error": "..."},
            "sms":      {...},
            "email":    {...},
            "primary":  "whatsapp" or "sms" or "email" or None
        }
    """
    results = {"whatsapp": None, "sms": None, "email": None, "primary": None}

    if prefer == "sms":
        order = ["sms", "whatsapp", "email"]
    elif prefer == "email":
        order = ["email", "sms", "whatsapp"]
    else:
        order = ["whatsapp", "sms", "email"]

    for channel in order:
        if results["primary"]:
            break
        if channel == "whatsapp" and phone:
            ok, err = send_whatsapp(db, tenant, phone, body_text)
            results["whatsapp"] = {"ok": ok, "error": err}
            if ok:
                results["primary"] = "whatsapp"
        elif channel == "sms" and phone:
            ok, err = send_sms(db, tenant, phone, body_text)
            results["sms"] = {"ok": ok, "error": err}
            if ok:
                results["primary"] = "sms"
        elif channel == "email" and email:
            ok, err = send_email(db, tenant, email, subject, body_text)
            results["email"] = {"ok": ok, "error": err}
            if ok:
                results["primary"] = "email"

    return results