"""Platform-wide email + WhatsApp overview and control.

Super Admin uses this to:
    - See every tenant's communication channels at once
    - Configure / disconnect channels on behalf of any tenant
    - Send test messages on behalf of any tenant

Endpoints:
    GET  /api/v1/platform/email/overview
    GET  /api/v1/platform/whatsapp/overview
    GET  /api/v1/platform/comms/health
    POST /api/v1/platform/tenants/{id}/whatsapp/configure
    POST /api/v1/platform/tenants/{id}/whatsapp/disconnect
    POST /api/v1/platform/tenants/{id}/whatsapp/priority
    POST /api/v1/platform/tenants/{id}/whatsapp/send
    POST /api/v1/platform/tenants/{id}/email/configure
    POST /api/v1/platform/tenants/{id}/email/send
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import Tenant, User
from .models_email import TenantEmailAccount, EmailLog
from .models_integrations import TenantIntegration
from .security import decode_token_strict, audit

logger = logging.getLogger(__name__)

router = APIRouter()

_bearer = HTTPBearer(auto_error=False)


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_platform_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(_db),
):
    if creds is None:
        raise HTTPException(401, "Authentication required")
    try:
        p = decode_token_strict(creds.credentials, settings.jwt_secret, settings.jwt_algorithm)
    except ValueError as exc:
        raise HTTPException(401, str(exc))
    user = db.get(User, p.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid user")
    if user.role not in ("platform_admin", "super_admin"):
        raise HTTPException(403, "Platform admin access required")
    return user


# ===========================================================================
# OVERVIEW ENDPOINTS (already built — kept for continuity)
# ===========================================================================

@router.get("/api/v1/platform/email/overview")
def email_overview(user=Depends(_require_platform_admin), db: Session = Depends(_db)):
    tenants = db.scalars(select(Tenant).order_by(Tenant.name)).all()
    tenant_ids = [t.id for t in tenants]

    accounts = db.scalars(
        select(TenantEmailAccount).where(TenantEmailAccount.tenant_id.in_(tenant_ids))
    ).all() if tenant_ids else []

    by_tenant: dict[str, list] = {}
    for a in accounts:
        by_tenant.setdefault(a.tenant_id, []).append(a)

    since = datetime.utcnow() - timedelta(hours=24)
    log_rows = db.execute(
        select(EmailLog.tenant_id, EmailLog.outcome, func.count(EmailLog.id))
        .where(EmailLog.created_at >= since)
        .group_by(EmailLog.tenant_id, EmailLog.outcome)
    ).all()
    log_stats: dict[str, dict] = {}
    for tid, outcome, count in log_rows:
        log_stats.setdefault(tid, {})[outcome or "unknown"] = int(count)

    items = []
    for t in tenants:
        accs = by_tenant.get(t.id, [])
        items.append({
            "tenant_id": t.id,
            "tenant_name": t.name,
            "tenant_slug": t.slug,
            "industry": t.industry,
            "status": t.status,
            "account_count": len(accs),
            "active_count": sum(1 for a in accs if a.is_active),
            "auto_reply_count": sum(1 for a in accs if a.auto_reply_enabled),
            "accounts": [
                {
                    "id": a.id,
                    "label": a.label,
                    "provider": a.provider,
                    "email_address": a.email_address,
                    "role": a.role,
                    "is_active": a.is_active,
                    "auto_reply_enabled": a.auto_reply_enabled,
                    "last_checked_at": a.last_checked_at.isoformat() if a.last_checked_at else None,
                    "last_error": a.last_error,
                }
                for a in accs
            ],
            "activity_24h": log_stats.get(t.id, {}),
        })

    totals = {
        "tenants": len(tenants),
        "tenants_with_email": sum(1 for x in items if x["account_count"] > 0),
        "total_accounts": sum(x["account_count"] for x in items),
        "total_active": sum(x["active_count"] for x in items),
        "total_errors": sum(1 for x in items for a in x["accounts"] if a["last_error"]),
    }
    return {"totals": totals, "items": items}


@router.get("/api/v1/platform/whatsapp/overview")
def whatsapp_overview(user=Depends(_require_platform_admin), db: Session = Depends(_db)):
    tenants = db.scalars(select(Tenant).order_by(Tenant.name)).all()

    try:
        from .whatsapp_channels import all_channels
    except Exception:
        all_channels = None

    items = []
    for t in tenants:
        state = None
        if all_channels:
            try:
                state = all_channels(db, t.id)
            except Exception as exc:
                logger.debug("all_channels failed for %s: %s", t.id, exc)

        openwa = (state or {}).get("openwa") or {}
        meta = (state or {}).get("meta") or {}

        items.append({
            "tenant_id": t.id,
            "tenant_name": t.name,
            "tenant_slug": t.slug,
            "industry": t.industry,
            "status": t.status,
            "openwa_connected": bool(openwa.get("connected")),
            "openwa_status": openwa.get("status"),
            "openwa_phone": openwa.get("connected_phone"),
            "meta_connected": bool(meta.get("connected")),
            "meta_status": meta.get("status"),
            "meta_phone": meta.get("connected_phone"),
            "priority": (state or {}).get("priority") or "openwa",
            "active": (state or {}).get("active"),
        })

    totals = {
        "tenants": len(tenants),
        "with_openwa": sum(1 for x in items if x["openwa_connected"]),
        "with_meta": sum(1 for x in items if x["meta_connected"]),
        "with_any_channel": sum(1 for x in items if x["openwa_connected"] or x["meta_connected"]),
    }
    return {"totals": totals, "items": items}


@router.get("/api/v1/platform/comms/health")
def comms_health(user=Depends(_require_platform_admin), db: Session = Depends(_db)):
    since = datetime.utcnow() - timedelta(hours=1)

    try:
        from .email_poller import _poller_task
        poller_running = bool(_poller_task and not _poller_task.done())
    except Exception:
        poller_running = None

    email_processed_1h = db.scalar(
        select(func.count(EmailLog.id)).where(EmailLog.created_at >= since)
    ) or 0

    integrations = db.scalar(
        select(func.count(TenantIntegration.id))
        .where(TenantIntegration.status == "connected")
    ) or 0

    return {
        "email_poller_running": poller_running,
        "email_processed_last_1h": int(email_processed_1h),
        "connected_integrations": int(integrations),
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


# ===========================================================================
# WHATSAPP — configure / disconnect / priority / send
# ===========================================================================

class WhatsAppConfigureRequest(BaseModel):
    provider: str = Field(pattern="^(openwa|meta)$")
    # OpenWA fields
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    session_id: Optional[str] = None
    # Meta fields
    access_token: Optional[str] = None
    phone_number_id: Optional[str] = None


class WhatsAppPriorityRequest(BaseModel):
    priority: str = Field(pattern="^(openwa|meta)$")


class WhatsAppSendRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=32)
    text: str = Field(min_length=1, max_length=4000)


@router.post("/api/v1/platform/tenants/{tenant_id}/whatsapp/configure")
async def platform_whatsapp_configure(
    tenant_id: str,
    payload: WhatsAppConfigureRequest,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    from .whatsapp_channels import configure_channel

    provider = payload.provider
    if provider == "openwa":
        if not all([payload.base_url, payload.api_key, payload.session_id]):
            raise HTTPException(400, "OpenWA requires base_url, api_key and session_id")
        # Validate credentials against the OpenWA API
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    payload.base_url.rstrip("/") + "/api/sessions/" + payload.session_id,
                    headers={"X-API-Key": payload.api_key},
                )
                r.raise_for_status()
                session = r.json()
                if str(session.get("status") or "").lower() != "ready":
                    raise ValueError("OpenWA session is not ready (status=" + str(session.get("status") or "unknown") + ")")
                connected_phone = session.get("phoneNumber") or session.get("phone")
        except Exception as exc:
            raise HTTPException(400, "OpenWA credentials could not be validated: " + str(exc))
        result = configure_channel(
            db, tenant_id, "openwa",
            {"base_url": payload.base_url, "api_key": payload.api_key, "session_id": payload.session_id},
            connected_phone, None,
        )
    else:  # meta
        if not all([payload.access_token, payload.phone_number_id]):
            raise HTTPException(400, "Meta requires access_token and phone_number_id")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://graph.facebook.com/v23.0/" + payload.phone_number_id,
                    headers={"Authorization": "Bearer " + payload.access_token},
                )
                r.raise_for_status()
                info = r.json()
                connected_phone = info.get("display_phone_number")
                display_name = info.get("verified_name")
        except Exception as exc:
            raise HTTPException(400, "Meta credentials could not be validated: " + str(exc))
        result = configure_channel(
            db, tenant_id, "meta",
            {"access_token": payload.access_token, "phone_number_id": payload.phone_number_id},
            connected_phone, display_name,
        )

    try:
        audit(db, tenant_id=tenant_id, actor_id=user.id,
              action="platform.whatsapp_configured", target_type="tenant",
              target_id=tenant_id, detail={"provider": provider})
    except Exception:
        pass

    return result


@router.post("/api/v1/platform/tenants/{tenant_id}/whatsapp/disconnect")
def platform_whatsapp_disconnect(
    tenant_id: str,
    provider: str,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    if provider not in ("openwa", "meta"):
        raise HTTPException(400, "provider must be openwa or meta")

    from .whatsapp_channels import disconnect_channel
    result = disconnect_channel(db, tenant_id, provider)

    try:
        audit(db, tenant_id=tenant_id, actor_id=user.id,
              action="platform.whatsapp_disconnected", target_type="tenant",
              target_id=tenant_id, detail={"provider": provider})
    except Exception:
        pass

    return result


@router.post("/api/v1/platform/tenants/{tenant_id}/whatsapp/priority")
def platform_whatsapp_priority(
    tenant_id: str,
    payload: WhatsAppPriorityRequest,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    from .whatsapp_channels import set_priority, all_channels
    set_priority(db, tenant_id, payload.priority)

    try:
        audit(db, tenant_id=tenant_id, actor_id=user.id,
              action="platform.whatsapp_priority_set", target_type="tenant",
              target_id=tenant_id, detail={"priority": payload.priority})
    except Exception:
        pass

    return all_channels(db, tenant_id)


@router.post("/api/v1/platform/tenants/{tenant_id}/whatsapp/send")
async def platform_whatsapp_send(
    tenant_id: str,
    payload: WhatsAppSendRequest,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    from .whatsapp_channels import send_text_with_failover
    try:
        result = await send_text_with_failover(db, tenant_id, settings, payload.phone, payload.text)
    except Exception as exc:
        logger.exception("platform whatsapp send failed tenant=%s", tenant_id)
        raise HTTPException(502, "Send failed: " + str(exc))

    if not result.get("ok"):
        logger.warning("platform whatsapp provider did not accept send tenant=%s error=%s",
                       tenant_id, result.get("error") or "unknown")
        raise HTTPException(502, "WhatsApp send failed: " + str(result.get("error") or "provider error"))

    try:
        audit(db, tenant_id=tenant_id, actor_id=user.id,
              action="platform.whatsapp_sent", target_type="tenant",
              target_id=tenant_id, detail={"phone": payload.phone, "len": len(payload.text),
                                           "channel": result.get("channel"), "fell_back": result.get("fell_back", False)})
    except Exception:
        pass

    return {"sent": True, "result": result}


# ===========================================================================
# EMAIL — configure / send
# ===========================================================================

class EmailConfigureRequest(BaseModel):
    label: str = Field(default="Primary mailbox", max_length=120)
    provider: str = Field(pattern="^(gmail|outlook|custom)$")
    email_address: EmailStr
    role: str = Field(default="support", pattern="^(contact|support|billing|general)$")
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None


class EmailSendRequest(BaseModel):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


@router.post("/api/v1/platform/tenants/{tenant_id}/email/configure")
def platform_email_configure(
    tenant_id: str,
    payload: EmailConfigureRequest,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    from .email_integration import build_config_from_input, create_account, test_connection_sync, test_smtp_connection_sync

    cfg = build_config_from_input(payload.provider, payload.model_dump(exclude_none=True))
    missing = [k for k in ("imap_host", "imap_port", "imap_user", "imap_password",
                           "smtp_host", "smtp_port", "smtp_user", "smtp_password")
               if not cfg.get(k)]
    if missing:
        raise HTTPException(400, "Missing email config fields: " + ", ".join(missing))

    test = test_connection_sync(cfg)
    if not test.get("ok"):
        raise HTTPException(400, "IMAP connection failed: " + str(test.get("error")))
    smtp_test = test_smtp_connection_sync(cfg)
    if not smtp_test.get("ok"):
        raise HTTPException(400, "SMTP connection failed: " + str(smtp_test.get("error")))

    result = create_account(
        db, tenant_id,
        label=payload.label,
        provider=payload.provider,
        email_address=payload.email_address,
        role=payload.role,
        cfg=cfg,
    )

    try:
        audit(db, tenant_id=tenant_id, actor_id=user.id,
              action="platform.email_configured", target_type="tenant",
              target_id=tenant_id, detail={"email": payload.email_address, "role": payload.role})
    except Exception:
        pass

    return result


@router.post("/api/v1/platform/tenants/{tenant_id}/email/send")
async def platform_email_send(
    tenant_id: str,
    payload: EmailSendRequest,
    account_id: Optional[str] = None,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    from .email_integration import decrypt_email_config, send_reply_smtp

    # Pick an account: specific one, or the first active mailbox
    if account_id:
        account = db.scalar(
            select(TenantEmailAccount).where(
                TenantEmailAccount.id == account_id,
                TenantEmailAccount.tenant_id == tenant_id,
            )
        )
    else:
        account = db.scalar(
            select(TenantEmailAccount).where(
                TenantEmailAccount.tenant_id == tenant_id,
                TenantEmailAccount.is_active == True,  # noqa: E712
            ).order_by(TenantEmailAccount.created_at.desc()).limit(1)
        )

    if not account:
        raise HTTPException(400, "No active email account configured for this tenant")

    try:
        cfg = decrypt_email_config(account.config_encrypted)
    except Exception as exc:
        raise HTTPException(500, "Could not decrypt mailbox credentials: " + str(exc))

    try:
        await send_reply_smtp(cfg, payload.to, payload.subject, payload.body)
    except Exception as exc:
        logger.exception("platform email send failed tenant=%s", tenant_id)
        raise HTTPException(502, "Send failed: " + str(exc))

    try:
        audit(db, tenant_id=tenant_id, actor_id=user.id,
              action="platform.email_sent", target_type="tenant",
              target_id=tenant_id, detail={"to": payload.to, "from": account.email_address})
    except Exception:
        pass

    return {"sent": True, "from": account.email_address, "to": payload.to}

# ===========================================================================
# PLATFORM-OWNED COMMUNICATIONS — campaigns to the platform owner's own customers.
# This endpoint must never target tenant businesses or use tenant-owned channels.
# ===========================================================================

class PlatformCampaignRecipient(BaseModel):
    name: str = Field(default="", max_length=160)
    phone: Optional[str] = Field(default=None, max_length=32)
    email: Optional[EmailStr] = None


class PlatformCampaignRequest(BaseModel):
    recipients: list[PlatformCampaignRecipient] = Field(min_length=1, max_length=1000)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=4000)
    channels: list[str] = Field(min_length=1)
    consent_confirmed: bool = False
    media_url: Optional[str] = Field(default=None, max_length=2000)
    media_type: Optional[str] = Field(default=None, pattern="^(image|video)$")


@router.post("/api/v1/platform/communications/campaign")
async def platform_communications_campaign(
    payload: PlatformCampaignRequest,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    """Send campaigns from platform-owned senders to the platform owner's own contacts."""
    channels = {str(c).strip().lower() for c in payload.channels}
    if not channels or not channels.issubset({"whatsapp", "email"}):
        raise HTTPException(400, "channels must contain whatsapp and/or email")
    if not payload.consent_confirmed:
        raise HTTPException(400, "Confirm that every recipient has opted in before sending")
    if payload.media_url and not payload.media_type:
        raise HTTPException(400, "media_type must be image or video when media_url is supplied")
    if payload.media_type and not payload.media_url:
        raise HTTPException(400, "media_url is required when media_type is supplied")
    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "Message body is required")

    from .notifications import send_email, send_platform_whatsapp, send_platform_whatsapp_media
    from .models_email import PlatformContactPreference, PlatformMarketingContact
    import re
    import uuid

    campaign_id = str(uuid.uuid4())
    results = []
    for recipient in payload.recipients:
        phone = (recipient.phone or "").strip() or None
        email = str(recipient.email).strip() if recipient.email else None
        if not phone and not email:
            raise HTTPException(400, "Every customer contact needs a phone number and/or email address")
        name = recipient.name.strip() or phone or email or "Customer"
        result = {"contact_id": None, "name": name, "channels": {}}
        phone_norm = re.sub(r"\\D", "", phone or "")
        email_norm = (email or "").strip().lower()
        phone_pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.phone_norm == phone_norm)) if phone_norm else None
        email_pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.email_norm == email_norm)) if email_norm else None
        saved_matches = []
        if phone_norm:
            saved = db.scalar(select(PlatformMarketingContact).where(PlatformMarketingContact.phone_norm == phone_norm))
            if saved:
                saved_matches.append(saved)
        if email_norm:
            saved = db.scalar(select(PlatformMarketingContact).where(PlatformMarketingContact.email_norm == email_norm))
            if saved and all(saved.id != row.id for row in saved_matches):
                saved_matches.append(saved)
        if saved_matches:
            result["contact_id"] = saved_matches[0].id
        whatsapp_contact_blocked = any(c.status != "active" or not c.whatsapp_opt_in for c in saved_matches)
        email_contact_blocked = any(c.status != "active" or not c.email_opt_in for c in saved_matches)

        if "whatsapp" in channels:
            if not phone:
                result["channels"]["whatsapp"] = {"sent": False, "status": "no_phone"}
            elif phone_pref and phone_pref.whatsapp_opt_out:
                result["channels"]["whatsapp"] = {"sent": False, "status": "opted_out"}
            elif whatsapp_contact_blocked:
                result["channels"]["whatsapp"] = {"sent": False, "status": "contact_not_opted_in"}
            else:
                msg = body.replace("{{name}}", name) + "\\n\\nReply STOP to opt out of AI Growth OS WhatsApp campaigns."
                try:
                    delivery = await send_platform_whatsapp_media(phone, payload.media_url, payload.media_type or "image", msg) if payload.media_url else await send_platform_whatsapp(phone, msg)
                    result["channels"]["whatsapp"] = delivery if isinstance(delivery, dict) else {"sent": bool(delivery), "status": "sent" if delivery else "failed"}
                except Exception as exc:
                    logger.warning("platform customer WhatsApp campaign failed: %s", exc)
                    result["channels"]["whatsapp"] = {"sent": False, "status": "provider_error"}

        if "email" in channels:
            if not email:
                result["channels"]["email"] = {"sent": False, "status": "no_email"}
            elif email_pref and email_pref.email_opt_out:
                result["channels"]["email"] = {"sent": False, "status": "opted_out"}
            elif email_contact_blocked:
                result["channels"]["email"] = {"sent": False, "status": "contact_not_opted_in"}
            else:
                msg = body.replace("{{name}}", name) + "\\n\\nTo stop AI Growth OS emails, reply UNSUBSCRIBE."
                try:
                    delivery = await send_email(email, payload.subject.strip() or "AI Growth OS", msg)
                    result["channels"]["email"] = delivery if isinstance(delivery, dict) else {"sent": bool(delivery), "status": "sent" if delivery else "failed"}
                except Exception as exc:
                    logger.warning("platform customer email campaign failed: %s", exc)
                    result["channels"]["email"] = {"sent": False, "status": "provider_error"}

        results.append(result)
        try:
            audit(
                db, tenant_id=None, actor_id=user.id,
                action="platform.customer_communication_campaign",
                target_type="platform_customer_contact",
                target_id=result.get("contact_id") or "manual-recipient",
                detail={
                    "campaign_id": campaign_id,
                    "name": name,
                    "channels": sorted(channels),
                    "delivery": {
                        channel: {"sent": bool(outcome.get("sent")), "status": outcome.get("status", "unknown")}
                        for channel, outcome in result["channels"].items()
                    },
                    "consent_confirmed": True,
                },
            )
        except Exception:
            logger.exception("could not persist platform campaign audit result")

    return {
        "campaign_id": campaign_id,
        "selected": len(results),
        "sent": sum(1 for item in results for channel in item["channels"].values() if channel.get("sent")),
        "results": results,
    }


@router.get("/api/v1/platform/marketing/campaign-history")
def platform_marketing_campaign_history(
    limit: int = 100,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    """Return persisted per-recipient delivery outcomes from the platform audit ledger."""
    import json
    from .models_growth import AuditLog
    rows = db.scalars(
        select(AuditLog).where(AuditLog.action == "platform.customer_communication_campaign")
        .order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500))
    ).all()
    items = []
    for row in rows:
        try:
            detail = json.loads(row.detail_json or "{}")
        except Exception:
            detail = {}
        items.append({
            "id": row.id,
            "campaign_id": detail.get("campaign_id"),
            "contact_id": row.target_id if row.target_id != "manual-recipient" else None,
            "name": detail.get("name", "External contact"),
            "channels": detail.get("channels", []),
            "delivery": detail.get("delivery", {}),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return {"items": items, "count": len(items)}

# ===========================================================================
# PLATFORM EMAIL INBOX — platform mailbox only (independent of tenant accounts).
# Configure PLATFORM_EMAIL_* environment variables in Render to enable it.
# ===========================================================================

class PlatformEmailReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


@router.get("/api/v1/platform/communications/email/inbox")
async def platform_email_inbox(
    limit: int = 100,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    import asyncio
    import uuid
    from datetime import datetime
    from .models_email import PlatformEmailMessage
    cfg = {
        "imap_host": settings.platform_email_imap_host,
        "imap_port": settings.platform_email_imap_port,
        "imap_user": settings.platform_email_imap_user,
        "imap_password": settings.platform_email_imap_password,
        "smtp_host": settings.platform_email_smtp_host,
        "smtp_port": settings.platform_email_smtp_port,
        "smtp_user": settings.platform_email_smtp_user,
        "smtp_password": settings.platform_email_smtp_password,
        "smtp_starttls": settings.platform_email_smtp_starttls,
    }
    configured = all(cfg.get(k) for k in ("imap_host", "imap_port", "imap_user", "imap_password"))
    poll_error = None
    if configured:
        try:
            from .email_integration import fetch_new_messages_sync
            messages = await asyncio.to_thread(fetch_new_messages_sync, cfg, 50)
            from email.utils import parseaddr
            from .models_email import PlatformContactPreference
            newly_received = []
            for msg in messages:
                mid = (msg.get("message_id") or "").strip()
                if not mid:
                    mid = "platform-inbox-" + str(msg.get("uid") or uuid.uuid4())
                existing = db.scalar(select(PlatformEmailMessage).where(PlatformEmailMessage.message_id == mid))
                if existing:
                    continue
                received_at = None
                try:
                    received_at = datetime.fromisoformat(msg["date"]) if msg.get("date") else None
                except Exception:
                    pass
                sender_raw = msg.get("from") or ""
                sender_email = (parseaddr(sender_raw)[1] or sender_raw).strip().lower()
                message_body = msg.get("text") or ""
                subject = msg.get("subject") or ""
                lines = {line.strip().lower() for line in message_body.splitlines()}
                unsubscribe = ("unsubscribe" in subject.lower() or bool(lines & {"unsubscribe", "unsubscribe me", "stop", "opt out", "opt-out", "remove me"}))
                status = "unsubscribed" if unsubscribe else "unread"
                if unsubscribe and sender_email:
                    pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.email_norm == sender_email))
                    if not pref:
                        pref = PlatformContactPreference(id=str(uuid.uuid4()), email_norm=sender_email)
                        db.add(pref)
                    pref.email_opt_out = True
                    pref.updated_at = datetime.utcnow()
                inbox_row = PlatformEmailMessage(
                    id=str(uuid.uuid4()), message_id=mid,
                    from_address=sender_raw,
                    to_address=msg.get("to") or settings.platform_email_address,
                    subject=subject, body=message_body,
                    received_at=received_at, status=status,
                )
                db.add(inbox_row)
                newly_received.append((inbox_row, sender_email, unsubscribe))
            db.commit()
            # Auto-reply only for newly fetched messages, only when a matching active
            # template has explicitly enabled auto_reply, and never to opted-out contacts.
            from .routes_platform_templates import choose_template
            from .models_email import PlatformContactPreference
            from .email_integration import send_reply_smtp
            for inbox_row, sender_email, unsubscribe in newly_received:
                if unsubscribe or not sender_email:
                    continue
                pref = db.scalar(select(PlatformContactPreference).where(
                    PlatformContactPreference.email_norm == sender_email
                ))
                if pref and pref.email_opt_out:
                    continue
                template = choose_template(db, "email", inbox_row.body, inbox_row.subject)
                if not template:
                    continue
                try:
                    await send_reply_smtp(
                        cfg, sender_email, template.subject.strip() or ("Re: " + inbox_row.subject if inbox_row.subject else "AI Growth OS"),
                        template.body.strip(), in_reply_to=inbox_row.message_id, references=inbox_row.message_id,
                    )
                    inbox_row.reply_text = template.body.strip()
                    inbox_row.replied_at = datetime.utcnow()
                    inbox_row.status = "auto_replied"
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("Platform email template auto-reply failed message=%s", inbox_row.id)
        except Exception as exc:
            db.rollback()
            logger.warning("platform email inbox poll failed: %s", exc)
            poll_error = "Inbox polling failed. Check the platform mailbox credentials and provider logs."
    rows = db.scalars(select(PlatformEmailMessage).order_by(PlatformEmailMessage.created_at.desc()).limit(min(max(limit, 1), 300))).all()
    return {
        "configured": configured and bool(settings.platform_email_smtp_host and settings.platform_email_smtp_user and settings.platform_email_smtp_password),
        "poll_error": poll_error,
        "from_address": settings.platform_email_address or settings.platform_email_smtp_user or None,
        "items": [{
            "id": m.id, "from_address": m.from_address, "to_address": m.to_address,
            "subject": m.subject, "body": m.body, "status": m.status,
            "received_at": m.received_at.isoformat() if m.received_at else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "replied_at": m.replied_at.isoformat() if m.replied_at else None,
        } for m in rows],
    }


@router.post("/api/v1/platform/communications/email/inbox/{message_id}/reply")
async def platform_email_inbox_reply(
    message_id: str,
    payload: PlatformEmailReplyRequest,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    from datetime import datetime
    from .models_email import PlatformEmailMessage
    from .email_integration import send_reply_smtp
    row = db.get(PlatformEmailMessage, message_id)
    if not row:
        raise HTTPException(404, "Inbox message not found")
    required = (settings.platform_email_smtp_host, settings.platform_email_smtp_port,
                settings.platform_email_smtp_user, settings.platform_email_smtp_password)
    if not all(required):
        raise HTTPException(503, "Platform SMTP is not configured in Render environment settings")
    cfg = {
        "smtp_host": settings.platform_email_smtp_host,
        "smtp_port": settings.platform_email_smtp_port,
        "smtp_user": settings.platform_email_smtp_user,
        "smtp_password": settings.platform_email_smtp_password,
        "smtp_starttls": settings.platform_email_smtp_starttls,
        "smtp_use_tls": settings.platform_email_smtp_use_tls,
    }
    try:
        await send_reply_smtp(
            cfg, row.from_address, row.subject, payload.body.strip(),
            in_reply_to=row.message_id, references=row.message_id,
        )
    except Exception as exc:
        logger.warning("platform email reply failed message=%s: %s", message_id, exc)
        raise HTTPException(502, "Platform email reply failed; check SMTP configuration")
    row.replied_at = datetime.utcnow()
    row.reply_text = payload.body.strip()
    row.status = "replied"
    db.commit()
    try:
        audit(db, tenant_id=None, actor_id=user.id, action="platform.email_replied",
              target_type="platform_email_message", target_id=row.id,
              detail={"to": row.from_address})
    except Exception:
        pass
    return {"sent": True, "message_id": row.id, "to": row.from_address}


# ===========================================================================
# PLATFORM WHATSAPP INBOX — configure the platform OpenWA webhook to this URL.
# The webhook secret must be set; tenant WhatsApp sessions remain untouched.
# ===========================================================================

class PlatformWhatsAppReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.get("/api/v1/platform/communications/whatsapp/inbox")
def platform_whatsapp_inbox(
    limit: int = 100,
    phone: str = "",
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    from .models_email import PlatformWhatsAppMessage
    q = select(PlatformWhatsAppMessage)
    if phone:
        q = q.where(PlatformWhatsAppMessage.phone == phone)
    rows = db.scalars(q.order_by(PlatformWhatsAppMessage.created_at.desc()).limit(min(max(limit, 1), 300))).all()
    return {
        "configured": bool((settings.notification_whatsapp_openwa_base_url or settings.openwa_base_url) and (settings.notification_whatsapp_openwa_api_key or settings.openwa_api_key) and (settings.notification_whatsapp_openwa_session_id or settings.openwa_session_id)),
        "webhook_url": settings.api_public_url.rstrip("/") + "/api/v1/webhooks/platform/openwa",
        "webhook_secret_configured": bool(settings.openwa_webhook_secret),
        "items": [{
            "id": m.id, "phone": m.phone, "contact_name": m.contact_name,
            "body": m.body, "direction": m.direction, "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in rows],
    }


@router.post("/api/v1/webhooks/platform/openwa")
async def platform_openwa_webhook(request: Request, db: Session = Depends(_db)):
    """Receive OpenWA's actual message.received envelope and authenticate its HMAC."""
    import json
    import uuid
    import re
    import hmac
    from datetime import datetime
    from .models_email import PlatformWhatsAppMessage, PlatformContactPreference

    secret = settings.openwa_webhook_secret or ""
    if not secret:
        raise HTTPException(503, "Platform OpenWA webhook secret is not configured")

    raw = await request.body()
    signature = request.headers.get("X-OpenWA-Signature") or request.headers.get("X-Webhook-Signature")
    from .integrations import WhatsAppAdapter
    if not WhatsAppAdapter.verify_webhook(raw, signature, secret):
        raise HTTPException(401, "Invalid OpenWA webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid webhook JSON")

    if payload.get("event") != "message.received":
        return {"ok": True, "ignored": True}

    # OpenWA server.ts dispatches data as its messageLogs logItem:
    # {messageId, sessionId, fromMe, chatId, sender, senderName, text, type, timestamp}
    data = payload.get("data") or {}
    chat_id = str(data.get("chatId") or "")
    sender = str(data.get("sender") or chat_id)
    if data.get("fromMe") is True or chat_id.endswith("@g.us") or sender.endswith("@g.us"):
        return {"ok": True, "ignored": True}

    body = str(data.get("text") or data.get("body") or "").strip()
    raw_phone = sender.split("@", 1)[0].strip()
    phone_norm = re.sub(r"\D", "", raw_phone)
    if not phone_norm or len(phone_norm) < 7 or not body:
        return {"ok": True, "ignored": True}
    phone = phone_norm
    provider_id = str(data.get("messageId") or data.get("id") or "").strip() or None

    if provider_id:
        existing = db.scalar(select(PlatformWhatsAppMessage).where(
            PlatformWhatsAppMessage.provider_message_id == provider_id
        ))
        if existing:
            return {"ok": True, "duplicate": True}

    command = body.lower().strip()
    pref = db.scalar(select(PlatformContactPreference).where(
        PlatformContactPreference.phone_norm == phone_norm
    ))
    opt_out = command in {"stop", "unsubscribe", "cancel", "end", "quit"}
    opt_in = command in {"start", "unstop", "subscribe"}
    if opt_out or opt_in:
        if not pref:
            pref = PlatformContactPreference(id=str(uuid.uuid4()), phone_norm=phone_norm)
            db.add(pref)
        pref.whatsapp_opt_out = bool(opt_out)
        pref.updated_at = datetime.utcnow()

    row = PlatformWhatsAppMessage(
        id=str(uuid.uuid4()), provider_message_id=provider_id, phone=phone,
        contact_name=(data.get("senderName") or None),
        body=body, direction="inbound", status="received",
    )
    db.add(row)
    db.commit()

    if opt_out or opt_in:
        try:
            from .notifications import send_platform_whatsapp
            reply = (
                "You are opted out of AI Growth OS WhatsApp campaigns. Reply START if you want to opt in again."
                if opt_out else
                "You are opted in to AI Growth OS WhatsApp updates."
            )
            await send_platform_whatsapp(phone, reply)
        except Exception:
            logger.exception("Platform WhatsApp consent acknowledgement failed")
    elif not (pref and pref.whatsapp_opt_out):
        # One template response per newly persisted inbound provider message.
        from .routes_platform_templates import choose_template
        template = choose_template(db, "whatsapp", body)
        if template:
            try:
                from .notifications import send_platform_whatsapp
                result = await send_platform_whatsapp(phone, template.body.strip())
                if result.get("sent"):
                    outbound = PlatformWhatsAppMessage(
                        id=str(uuid.uuid4()), phone=phone, contact_name=row.contact_name,
                        body=template.body.strip(), direction="outbound", status="auto_replied",
                    )
                    db.add(outbound)
                    row.status = "auto_replied"
                    db.commit()
            except Exception:
                db.rollback()
                logger.exception("Platform WhatsApp template auto-reply failed message=%s", row.id)
    return {"ok": True, "message_id": row.id}


@router.post("/api/v1/platform/communications/whatsapp/inbox/{message_id}/reply")
async def platform_whatsapp_inbox_reply(
    message_id: str,
    payload: PlatformWhatsAppReplyRequest,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    import uuid
    from .models_email import PlatformWhatsAppMessage
    inbound = db.get(PlatformWhatsAppMessage, message_id)
    if not inbound or inbound.direction != "inbound":
        raise HTTPException(404, "Inbound WhatsApp message not found")
    from .notifications import send_platform_whatsapp
    result = await send_platform_whatsapp(inbound.phone, payload.body.strip())
    if not result.get("sent"):
        raise HTTPException(502, "Platform WhatsApp send failed: " + str(result.get("status") or "provider error"))
    outbound = PlatformWhatsAppMessage(
        id=str(uuid.uuid4()), phone=inbound.phone, contact_name=inbound.contact_name,
        body=payload.body.strip(), direction="outbound", status="sent",
    )
    db.add(outbound)
    inbound.status = "replied"
    db.commit()
    try:
        audit(db, tenant_id=None, actor_id=user.id, action="platform.whatsapp_replied",
              target_type="platform_whatsapp_message", target_id=inbound.id,
              detail={"phone": inbound.phone})
    except Exception:
        pass
    return {"sent": True, "message_id": outbound.id, "phone": inbound.phone}


# ===========================================================================
# SUPER ADMIN INBOX: tenant-owned channels (never platform-owned credentials)
# ===========================================================================
@router.get("/api/v1/platform/tenant-comms/email/inbox")
def tenant_email_inbox(limit: int = 100, tenant_id: str = "",
                       user=Depends(_require_platform_admin), db: Session = Depends(_db)):
    from .models import Tenant
    from .models_email import EmailLog
    q = select(EmailLog, TenantEmailAccount, Tenant).join(
        TenantEmailAccount, TenantEmailAccount.id == EmailLog.account_id
    ).join(Tenant, Tenant.id == EmailLog.tenant_id)
    if tenant_id:
        q = q.where(EmailLog.tenant_id == tenant_id)
    rows = db.execute(q.order_by(EmailLog.created_at.desc()).limit(min(max(limit, 1), 300))).all()
    return {"items": [{
        "id": log.id, "tenant_id": log.tenant_id, "tenant_name": tenant.name,
        "account_id": account.id, "account_email": account.email_address,
        "from_address": log.from_address, "to_address": log.to_address,
        "subject": log.subject, "body": log.inbound_body or "",
        "reply_text": log.reply_text, "outcome": log.outcome, "error": log.error,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    } for log, account, tenant in rows]}


@router.post("/api/v1/platform/tenant-comms/email/inbox/{message_id}/reply")
async def tenant_email_inbox_reply(message_id: str, payload: PlatformEmailReplyRequest,
                                   user=Depends(_require_platform_admin), db: Session = Depends(_db)):
    from .email_integration import decrypt_email_config, send_reply_smtp
    row = db.get(EmailLog, message_id)
    if not row:
        raise HTTPException(404, "Tenant email message not found")
    account = db.scalar(select(TenantEmailAccount).where(
        TenantEmailAccount.id == row.account_id, TenantEmailAccount.tenant_id == row.tenant_id
    ))
    if not account or not account.is_active:
        raise HTTPException(409, "Tenant email account is inactive or unavailable")
    try:
        cfg = decrypt_email_config(account.config_encrypted)
        await send_reply_smtp(cfg, row.from_address, row.subject, payload.body.strip(),
                              in_reply_to=row.message_id, references=row.references_header or row.message_id)
    except Exception as exc:
        logger.warning("admin tenant email reply failed log=%s: %s", message_id, exc)
        raise HTTPException(502, "Reply failed using the tenant's configured mailbox")
    row.reply_text = payload.body.strip()
    row.outcome = "admin_replied"
    row.error = None
    db.commit()
    return {"sent": True, "to": row.from_address, "tenant_id": row.tenant_id}


@router.get("/api/v1/platform/tenant-comms/whatsapp/inbox")
def tenant_whatsapp_inbox(limit: int = 100, tenant_id: str = "",
                          user=Depends(_require_platform_admin), db: Session = Depends(_db)):
    from .models import Tenant
    from .models_email import TenantWhatsAppMessage
    q = select(TenantWhatsAppMessage, Tenant).join(Tenant, Tenant.id == TenantWhatsAppMessage.tenant_id)
    if tenant_id:
        q = q.where(TenantWhatsAppMessage.tenant_id == tenant_id)
    rows = db.execute(q.order_by(TenantWhatsAppMessage.created_at.desc()).limit(min(max(limit, 1), 300))).all()
    return {"items": [{
        "id": msg.id, "tenant_id": msg.tenant_id, "tenant_name": tenant.name,
        "phone": msg.phone, "contact_name": msg.contact_name, "body": msg.body,
        "direction": msg.direction, "status": msg.status,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    } for msg, tenant in rows]}


@router.post("/api/v1/platform/tenant-comms/whatsapp/inbox/{message_id}/reply")
async def tenant_whatsapp_inbox_reply(message_id: str, payload: PlatformWhatsAppReplyRequest,
                                      user=Depends(_require_platform_admin), db: Session = Depends(_db)):
    import uuid
    from .models_email import TenantWhatsAppMessage
    from .whatsapp_channels import send_text_with_failover
    inbound = db.get(TenantWhatsAppMessage, message_id)
    if not inbound or inbound.direction != "inbound":
        raise HTTPException(404, "Tenant inbound WhatsApp message not found")
    try:
        result = await send_text_with_failover(db, inbound.tenant_id, settings, inbound.phone, payload.body.strip())
        if not result.get("ok"):
            raise HTTPException(502, "Tenant WhatsApp delivery failed: " + str(result.get("error") or "provider error"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin tenant WhatsApp reply failed message=%s: %s", message_id, exc)
        raise HTTPException(502, "Reply failed using the tenant's configured WhatsApp channel")
    outbound = TenantWhatsAppMessage(
        id=str(uuid.uuid4()), tenant_id=inbound.tenant_id, phone=inbound.phone,
        contact_name=inbound.contact_name, body=payload.body.strip(),
        direction="outbound", status="sent",
    )
    db.add(outbound)
    inbound.status = "replied"
    db.commit()
    return {"sent": True, "phone": inbound.phone, "tenant_id": inbound.tenant_id, "provider": result.get("channel")}


# ======================================================================
# PLATFORM-OWNED EXTERNAL CONTACT BOOK
# These contacts are independent of tenant customers, inboxes and senders.
# ======================================================================

class PlatformMarketingContactInput(BaseModel):
    name: str = Field(default="", max_length=160)
    phone: Optional[str] = Field(default=None, max_length=32)
    email: Optional[EmailStr] = None
    whatsapp_opt_in: bool = False
    email_opt_in: bool = False
    consent_source: Optional[str] = Field(default=None, max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=30)


class PlatformMarketingContactImport(BaseModel):
    contacts: list[PlatformMarketingContactInput] = Field(min_length=1, max_length=1000)


@router.get("/api/v1/platform/marketing/contacts")
def list_platform_marketing_contacts(
    query: str = "",
    limit: int = 200,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    from .models_email import PlatformMarketingContact
    q = select(PlatformMarketingContact).where(PlatformMarketingContact.status == "active")
    needle = query.strip().lower()
    if needle:
        like = "%" + needle.replace("%", "\\%").replace("_", "\\_") + "%"
        q = q.where(
            PlatformMarketingContact.name.ilike(like)
            | PlatformMarketingContact.phone.ilike(like)
            | PlatformMarketingContact.email.ilike(like)
            | PlatformMarketingContact.tags.ilike(like)
        )
    rows = db.scalars(q.order_by(PlatformMarketingContact.created_at.desc()).limit(min(max(limit, 1), 1000))).all()
    return {"items": [{
        "id": c.id, "name": c.name, "phone": c.phone, "email": c.email,
        "whatsapp_opt_in": c.whatsapp_opt_in, "email_opt_in": c.email_opt_in,
        "consent_source": c.consent_source, "tags": c.tags, "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in rows], "count": len(rows)}


@router.post("/api/v1/platform/marketing/contacts/import")
def import_platform_marketing_contacts(
    payload: PlatformMarketingContactImport,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    """Import only platform-owned external contacts; consent is explicit per channel."""
    import re
    import uuid
    from datetime import datetime
    from .models_email import PlatformMarketingContact, PlatformContactPreference

    imported = 0
    updated = 0
    rejected = []
    seen = set()
    for index, item in enumerate(payload.contacts):
        phone = (item.phone or "").strip() or None
        email = str(item.email).strip().lower() if item.email else None
        phone_norm = re.sub(r"\D", "", phone or "") or None
        email_norm = email or None
        if not phone_norm and not email_norm:
            rejected.append({"row": index + 1, "reason": "phone_or_email_required"})
            continue
        identities = [x for x in (("phone:" + phone_norm) if phone_norm else None, ("email:" + email_norm) if email_norm else None) if x]
        if any(identity in seen for identity in identities):
            rejected.append({"row": index + 1, "reason": "duplicate_in_import"})
            continue
        seen.update(identities)
        phone_contact = db.scalar(select(PlatformMarketingContact).where(PlatformMarketingContact.phone_norm == phone_norm)) if phone_norm else None
        email_contact = db.scalar(select(PlatformMarketingContact).where(PlatformMarketingContact.email_norm == email_norm)) if email_norm else None
        if phone_contact and email_contact and phone_contact.id != email_contact.id:
            rejected.append({"row": index + 1, "reason": "phone_and_email_belong_to_different_contacts"})
            continue
        contact = phone_contact or email_contact
        if not contact:
            contact = PlatformMarketingContact(id=str(uuid.uuid4()))
            db.add(contact)
            imported += 1
        else:
            updated += 1
        contact.name = item.name.strip() or contact.name or phone or email or "External contact"
        if phone:
            contact.phone = phone
            contact.phone_norm = phone_norm
        if email:
            contact.email = email
            contact.email_norm = email_norm
        # Consent is opt-in only; import never clears an existing opt-in.
        contact.whatsapp_opt_in = bool(contact.whatsapp_opt_in or item.whatsapp_opt_in)
        contact.email_opt_in = bool(contact.email_opt_in or item.email_opt_in)
        contact.consent_source = item.consent_source.strip() if item.consent_source else contact.consent_source
        contact.tags = ",".join(dict.fromkeys([t.strip() for t in item.tags if t.strip()])) or contact.tags or ""
        contact.status = "active"
        contact.updated_at = datetime.utcnow()
        # Preserve the pre-existing opt-out ledger used by the sending endpoint.
        # Apply explicit opt-ins to both matching opt-out ledger records, if present.
        pref_rows = []
        if phone_norm:
            pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.phone_norm == phone_norm))
            if pref:
                pref_rows.append(pref)
        if email_norm:
            pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.email_norm == email_norm))
            if pref and pref not in pref_rows:
                pref_rows.append(pref)
        for pref in pref_rows:
            if item.whatsapp_opt_in:
                pref.whatsapp_opt_out = False
            if item.email_opt_in:
                pref.email_opt_out = False
            pref.updated_at = datetime.utcnow()
    db.commit()
    try:
        audit(db, tenant_id=None, actor_id=user.id, action="platform.marketing_contacts_imported",
              target_type="platform_marketing_contact", target_id="bulk-import",
              detail={"imported": imported, "updated": updated, "rejected": len(rejected)})
    except Exception:
        pass
    return {"imported": imported, "updated": updated, "rejected": rejected}


@router.patch("/api/v1/platform/marketing/contacts/{contact_id}/consent")
def update_platform_marketing_contact_consent(
    contact_id: str,
    payload: PlatformMarketingContactInput,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    import re
    from datetime import datetime
    from .models_email import PlatformMarketingContact, PlatformContactPreference
    contact = db.get(PlatformMarketingContact, contact_id)
    if not contact:
        raise HTTPException(404, "Platform contact not found")
    phone_norm = re.sub(r"\D", "", contact.phone or "") or None
    email_norm = (contact.email or "").strip().lower() or None
    contact.whatsapp_opt_in = payload.whatsapp_opt_in
    contact.email_opt_in = payload.email_opt_in
    contact.consent_source = payload.consent_source.strip() if payload.consent_source else contact.consent_source
    contact.updated_at = datetime.utcnow()
    pref_rows = []
    if phone_norm:
        pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.phone_norm == phone_norm))
        if pref:
            pref_rows.append(pref)
    if email_norm:
        pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.email_norm == email_norm))
        if pref and pref not in pref_rows:
            pref_rows.append(pref)
    if not pref_rows:
        pref_rows.append(PlatformContactPreference(
            id=str(__import__("uuid").uuid4()), phone_norm=phone_norm, email_norm=email_norm,
            whatsapp_opt_out=not payload.whatsapp_opt_in, email_opt_out=not payload.email_opt_in,
        ))
        db.add(pref_rows[0])
    else:
        for pref in pref_rows:
            pref.whatsapp_opt_out = not payload.whatsapp_opt_in
            pref.email_opt_out = not payload.email_opt_in
            pref.updated_at = datetime.utcnow()
    db.commit()
    return {"id": contact.id, "whatsapp_opt_in": contact.whatsapp_opt_in,
            "email_opt_in": contact.email_opt_in, "updated_at": contact.updated_at.isoformat()}


@router.delete("/api/v1/platform/marketing/contacts/{contact_id}")
def archive_platform_marketing_contact(
    contact_id: str,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    from .models_email import PlatformMarketingContact
    contact = db.get(PlatformMarketingContact, contact_id)
    if not contact:
        raise HTTPException(404, "Platform contact not found")
    contact.status = "archived"
    contact.whatsapp_opt_in = False
    contact.email_opt_in = False
    import re
    from .models_email import PlatformContactPreference
    phone_norm = re.sub(r"\D", "", contact.phone or "") or None
    email_norm = (contact.email or "").strip().lower() or None
    if phone_norm:
        pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.phone_norm == phone_norm))
        if pref:
            pref.whatsapp_opt_out = True
            pref.email_opt_out = True
    if email_norm:
        pref = db.scalar(select(PlatformContactPreference).where(PlatformContactPreference.email_norm == email_norm))
        if pref:
            pref.whatsapp_opt_out = True
            pref.email_opt_out = True
    db.commit()
    return {"archived": True, "id": contact.id}
