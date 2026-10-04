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
from fastapi import APIRouter, Depends, HTTPException
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