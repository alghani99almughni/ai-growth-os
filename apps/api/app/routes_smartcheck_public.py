"""Public QR-first visitor registration backed by AI Growth OS PostgreSQL.

No Google Sheets, Apps Script URL, or bridge secret is required. Visitors may register
from a QR scan without installing the PWA; all requests begin pending approval.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import Tenant
from .models_growth import TenantSetting, PlatformSetting
from .models_security import VisitorPass, VisitorEvent
import hashlib
import secrets
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/v1/public/smartcheck", tags=["public-smartcheck-visitors"])
_ALLOWED_SCRIPT_HOSTS = {"script.google.com", "script.googleusercontent.com"}


class PublicVisitorRequest(BaseModel):
    visitor_name: str = Field(min_length=1, max_length=160)
    visitor_mobile: str = Field(min_length=5, max_length=32)
    purpose: str = Field(default="", max_length=240)
    destination: str = Field(default="", max_length=200)
    vehicle_number: str = Field(default="", max_length=40)


class GoogleScriptRedirectHandler(HTTPRedirectHandler):
    """Allow normal Apps Script redirects without allowing redirects to arbitrary hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_SCRIPT_HOSTS:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _tenant_feature_enabled(db, tenant_id: str) -> bool:
    feature_row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id, TenantSetting.key == "features"
    ))
    defaults_row = db.scalar(select(PlatformSetting).where(PlatformSetting.key == "feature_defaults"))
    try:
        features = json.loads(feature_row.value_json) if feature_row else {}
    except (TypeError, ValueError):
        features = {}
    try:
        defaults = json.loads(defaults_row.value_json) if defaults_row else {}
    except (TypeError, ValueError):
        defaults = {}
    return bool(features.get("security_visitor_management",
                             defaults.get("security_visitor_management", False)))


@router.post("/{tenant_slug}/visitor-requests")
def create_public_visitor_request(tenant_slug: str, body: PublicVisitorRequest):
    """Public QR visitor form; writes directly to the tenant-scoped SQL database."""
    db = SessionLocal()
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug.lower()))
        if not tenant or str(tenant.status).lower() not in {"active", "trial"}:
            raise HTTPException(404, "Visitor registration is unavailable for this tenant")
        if not _tenant_feature_enabled(db, tenant.id):
            raise HTTPException(403, "Security & Visitor Management is disabled for this tenant")

        raw_token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        visitor = VisitorPass(
            tenant_id=tenant.id,
            site_id=None,
            token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            visitor_name=body.visitor_name.strip(),
            visitor_mobile=body.visitor_mobile.strip(),
            purpose=body.purpose.strip(),
            destination=body.destination.strip(),
            vehicle_number=body.vehicle_number.strip().upper(),
            industry="apartment",
            status="pending",
            expires_at=now + timedelta(hours=24),
            created_by="public-qr-visitor",
        )
        db.add(visitor)
        db.flush()
        db.add(VisitorEvent(
            tenant_id=tenant.id,
            pass_id=visitor.id,
            actor_id="public-qr-visitor",
            event_type="visitor_request_created",
            details_json=json.dumps({"source": "qr_public_form", "status": "pending"}),
        ))
        db.commit()
        db.refresh(visitor)
        return {
            "ticket_id": visitor.id,
            "status": "pending",
            "message": "Visitor request submitted. Entry is not permitted until an authorized person approves it.",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, "Could not save visitor request. Please try again.") from None
    finally:
        db.close()
