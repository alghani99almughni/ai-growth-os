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

    try:
        audit(db, tenant_id=tenant_id, actor_id=user.id,
              action="platform.whatsapp_sent", target_type="tenant",
              target_id=tenant_id, detail={"phone": payload.phone, "len": len(payload.text)})
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

    from .email_integration import build_config_from_input, create_account, test_connection_sync

    cfg = build_config_from_input(payload.provider, payload.model_dump(exclude_none=True))
    missing = [k for k in ("imap_host", "imap_port", "imap_user", "imap_password",
                           "smtp_host", "smtp_port", "smtp_user", "smtp_password")
               if not cfg.get(k)]
    if missing:
        raise HTTPException(400, "Missing email config fields: " + ", ".join(missing))

    test = test_connection_sync(cfg)
    if not test.get("ok"):
        raise HTTPException(400, "IMAP connection failed: " + str(test.get("error")))

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
# PLATFORM-OWNED COMMUNICATIONS — campaigns to opted-in tenant contacts.
# This intentionally uses platform credentials, never tenant mailbox/channel keys.
# ===========================================================================

class PlatformCampaignRequest(BaseModel):
    tenant_ids: list[str] = Field(min_length=1, max_length=500)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=4000)
    channels: list[str] = Field(min_length=1)
    consent_confirmed: bool = False


@router.post("/api/v1/platform/communications/campaign")
async def platform_communications_campaign(
    payload: PlatformCampaignRequest,
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    """Send a platform-owned email/WhatsApp campaign to explicitly selected tenants.

    A campaign requires the admin to attest that every selected recipient opted in.
    It does not silently treat tenant registration as marketing consent.
    """
    channels = {str(c).strip().lower() for c in payload.channels}
    if not channels or not channels.issubset({"whatsapp", "email"}):
        raise HTTPException(400, "channels must contain whatsapp and/or email")
    if not payload.consent_confirmed:
        raise HTTPException(400, "Confirm that every selected recipient has opted in before sending")
    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "Message body is required")
    tenants = db.scalars(select(Tenant).where(Tenant.id.in_(set(payload.tenant_ids)))).all()
    by_id = {t.id: t for t in tenants}
    missing = [tid for tid in set(payload.tenant_ids) if tid not in by_id]
    if missing:
        raise HTTPException(404, "One or more selected tenants were not found")
    from .notifications import send_email, send_platform_whatsapp
    results = []
    for tid in payload.tenant_ids:
        tenant = by_id[tid]
        result = {"tenant_id": tenant.id, "tenant_name": tenant.name, "channels": {}}
        if "whatsapp" in channels:
            phone = tenant.whatsapp_number or tenant.phone
            if not phone:
                result["channels"]["whatsapp"] = {"sent": False, "status": "no_phone"}
            else:
                result["channels"]["whatsapp"] = await send_platform_whatsapp(phone, body)
        if "email" in channels:
            address = tenant.email
            if not address:
                owner = db.scalar(select(User).where(
                    User.tenant_id == tenant.id,
                    User.role.in_(["owner", "admin"]),
                    User.is_active == True,  # noqa: E712
                ).order_by(User.created_at.asc()).limit(1))
                address = owner.email if owner else None
            if not address:
                result["channels"]["email"] = {"sent": False, "status": "no_email"}
            else:
                result["channels"]["email"] = await send_email(
                    address,
                    payload.subject.strip() or "AI Growth OS",
                    body,
                )
        results.append(result)
        try:
            audit(db, tenant_id=tenant.id, actor_id=user.id,
                  action="platform.communication_campaign",
                  target_type="tenant", target_id=tenant.id,
                  detail={"channels": sorted(channels), "consent_confirmed": True})
        except Exception:
            pass
    return {
        "selected": len(results),
        "sent": sum(1 for r in results for c in r["channels"].values() if c.get("sent")),
        "results": results,
    }


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
                db.add(PlatformEmailMessage(
                    id=str(uuid.uuid4()), message_id=mid,
                    from_address=msg.get("from") or "",
                    to_address=msg.get("to") or settings.platform_email_address,
                    subject=msg.get("subject") or "", body=msg.get("text") or "",
                    received_at=received_at, status="unread",
                ))
            db.commit()
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
    }
    try:
        await send_reply_smtp(cfg, row.from_address, row.subject, payload.body.strip())
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
        "configured": bool(settings.notification_whatsapp_openwa_base_url and settings.notification_whatsapp_openwa_api_key and settings.notification_whatsapp_openwa_session_id),
        "webhook_url": settings.public_app_url.rstrip("/") + "/api/v1/webhooks/platform/openwa",
        "webhook_secret_configured": bool(settings.openwa_webhook_secret),
        "items": [{
            "id": m.id, "phone": m.phone, "contact_name": m.contact_name,
            "body": m.body, "direction": m.direction, "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in rows],
    }


@router.post("/api/v1/webhooks/platform/openwa")
async def platform_openwa_webhook(request: Request, db: Session = Depends(_db)):
    import json
    import uuid
    from .models_email import PlatformWhatsAppMessage
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
    data = payload.get("data") or {}
    if data.get("isGroup"):
        return {"ok": True, "ignored": True}
    phone = str(data.get("senderPhone") or data.get("from") or data.get("chatId") or "").split("@")[0].strip()
    body = str(data.get("body") or "").strip()
    if not phone or not body:
        return {"ok": True, "ignored": True}
    provider_id = str(data.get("id") or data.get("messageId") or "").strip() or None
    if provider_id:
        existing = db.scalar(select(PlatformWhatsAppMessage).where(PlatformWhatsAppMessage.provider_message_id == provider_id))
        if existing:
            return {"ok": True, "duplicate": True}
    contact = data.get("contact") or {}
    row = PlatformWhatsAppMessage(
        id=str(uuid.uuid4()), provider_message_id=provider_id, phone=phone,
        contact_name=(contact.get("pushName") or contact.get("name") or None),
        body=body, direction="inbound", status="received",
    )
    db.add(row)
    db.commit()
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
