"""Public onboarding + industry catalog endpoints.

Kept separate from main.py so the file stays clean.

Endpoints:
    GET  /api/v1/public/industries       list industry templates
    POST /api/v1/public/onboard/register self-serve signup with industry + hours
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Tenant, User
from .services import create_tenant, create_owner, hash_password
from .industry_templates import seed_industry_defaults, available_industries
from .industry_catalog import IndustryCatalogEntry
from .models_growth import TenantSetting

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BusinessHourRow(BaseModel):
    weekday: int = Field(ge=0, le=6)
    open_time: str = "09:00"
    close_time: str = "18:00"
    is_closed: bool = False
    is_24_hours: bool = False
    slot_interval_minutes: int = Field(default=30, ge=5, le=120)


class OnboardRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=160)
    industry: str = Field(min_length=2, max_length=80)
    owner_name: str = Field(min_length=2, max_length=160)
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=32)
    whatsapp_number: Optional[str] = Field(default=None, max_length=32)
    address: Optional[str] = None
    timezone: str = Field(default="Asia/Kolkata", max_length=60)
    business_hours: Optional[list[BusinessHourRow]] = None
    catalog_entry_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "business"


def _unique_slug(db: Session, base: str) -> str:
    slug = base
    n = 1
    while db.scalar(select(Tenant).where(Tenant.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
        if n > 100:
            slug = f"{base}-{uuid.uuid4().hex[:6]}"
            break
    return slug


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/public/industries")
def list_industries():
    """Public list of industries the platform supports."""
    return {"items": available_industries()}


@router.post("/api/v1/public/onboard/register", status_code=201)
def public_onboard(payload: OnboardRequest):
    """Self-serve signup. Creates tenant, owner, seeds industry defaults and hours.

    This is the public path — no authentication required.
    """
    db: Session = SessionLocal()
    try:
        catalog_entry = None
        if payload.catalog_entry_id:
            catalog_entry = db.get(IndustryCatalogEntry, payload.catalog_entry_id)
            if not catalog_entry or not catalog_entry.is_active:
                raise HTTPException(400, "Please select an active industry business type")

        if db.scalar(select(User).where(User.email == payload.owner_email.lower())):
            raise HTTPException(409, "Email already registered")

        slug = _unique_slug(db, _slugify(payload.business_name))

        tenant = create_tenant(db, payload.business_name, slug, payload.industry)
        tenant.phone = payload.phone
        tenant.whatsapp_number = payload.whatsapp_number
        tenant.address = payload.address
        tenant.timezone = payload.timezone or "Asia/Kolkata"
        db.commit()
        db.refresh(tenant)

        owner = create_owner(
            db,
            payload.owner_name,
            payload.owner_email,
            payload.owner_password,
            tenant,
        )

        # Seed hours (custom or default)
        from .booking import ensure_default_hours, seed_hours
        if payload.business_hours:
            seed_hours(db, tenant.id, payload.business_hours)
        else:
            ensure_default_hours(db, tenant.id)

        # Seed industry defaults (services, menu, knowledge)
        seed_industry_defaults(db, tenant, payload.industry)

        if catalog_entry:
            import json as _catalog_json
            selection = {
                "catalog_entry_id": catalog_entry.id,
                "category": catalog_entry.category,
                "business_type": catalog_entry.business_type,
                "roles": _catalog_json.loads(catalog_entry.roles_json or "[]"),
                "notes": None,
            }
            db.add(TenantSetting(id=str(uuid.uuid4()), tenant_id=tenant.id,
                                 key="industry_selection", value_json=_catalog_json.dumps(selection)))
            db.commit()

        # Minimal feature defaults — the tenant can tune later
        from .models_growth import TenantSetting
        import json as _json
        existing = db.scalar(select(TenantSetting).where(
            TenantSetting.tenant_id == tenant.id,
            TenantSetting.key == "features",
        ))
        if not existing:
            db.add(TenantSetting(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                key="features",
                value_json=_json.dumps({}),  # empty = use industry fallback
            ))
            db.commit()

        return {
            "tenant_id": tenant.id,
            "slug": tenant.slug,
            "owner_id": owner.id,
            "owner_email": owner.email,
            "dashboard_url": "/login",
            "customer_pwa_url": f"/customer?business={tenant.slug}",
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("public_onboard failed: %s", exc)
        raise HTTPException(500, "Could not complete signup. Please try again.")
    finally:
        db.close()