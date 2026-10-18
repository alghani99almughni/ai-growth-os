"""Tenant-scoped AEO/GEO profile and query APIs.

This first slice intentionally stores configuration and questions only. It does not
pretend to run live AI search checks; provider adapters and SSRF-safe auditing are
separate follow-up work.
"""
import re
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import User
from .models_visibility import VisibilityBrand, VisibilityCompetitor, VisibilityQuery

# Imported by main.py at the end of module initialization to avoid an import cycle.
from .main import get_current_user, get_db, require_tenant

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/visibility", tags=["AEO/GEO Visibility"])

def _authorize(user: User, tenant_id: str):
    require_tenant(user, tenant_id)
    if user.role not in ("platform_admin", "super_admin") and user.tenant_id != tenant_id:
        raise HTTPException(403, "Tenant access denied")

def _domain(value: str) -> str:
    value = value.strip()
    candidate = value if "://" in value else "https://" + value
    parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HTTPException(422, "Enter a valid website domain, for example https://example.com")
    if parts.username or parts.password or parts.port not in (None, 80, 443):
        raise HTTPException(422, "Website URL credentials and custom ports are not supported")
    host = parts.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or "." not in host:
        raise HTTPException(422, "Enter a public internet domain")
    if not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host:
        raise HTTPException(422, "Enter a valid public internet domain")
    return host

class BrandPayload(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    primary_domain: str = Field(min_length=3, max_length=253)
    description: str = Field(default="", max_length=4000)
    locale: str = Field(default="en", min_length=2, max_length=20)

class CompetitorPayload(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    domain: str = Field(min_length=3, max_length=253)
    notes: str = Field(default="", max_length=2000)

class QueryPayload(BaseModel):
    query_text: str = Field(min_length=3, max_length=500)
    intent: str = Field(default="informational", pattern="^(informational|local|comparison|transactional|navigational)$")
    locale: str = Field(default="en", min_length=2, max_length=20)
    topic: str = Field(default="", max_length=120)
    is_active: bool = True

def _brand_out(row):
    return {"id": row.id, "tenant_id": row.tenant_id, "name": row.name,
            "primary_domain": row.primary_domain, "description": row.description,
            "locale": row.locale, "created_at": row.created_at.isoformat() if row.created_at else None}

@router.get("/brand")
def get_brand(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = db.scalar(select(VisibilityBrand).where(VisibilityBrand.tenant_id == tenant_id).order_by(VisibilityBrand.created_at.asc()))
    return {"brand": _brand_out(row) if row else None}

@router.put("/brand")
def put_brand(tenant_id: str, payload: BrandPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = db.scalar(select(VisibilityBrand).where(VisibilityBrand.tenant_id == tenant_id).order_by(VisibilityBrand.created_at.asc()))
    if row is None:
        row = VisibilityBrand(tenant_id=tenant_id, name=payload.name.strip(), primary_domain=_domain(payload.primary_domain))
        db.add(row)
    row.name = payload.name.strip()
    row.primary_domain = _domain(payload.primary_domain)
    row.description = payload.description.strip()
    row.locale = payload.locale.strip()
    db.commit()
    db.refresh(row)
    return {"brand": _brand_out(row)}

@router.get("/competitors")
def list_competitors(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    rows = db.scalars(select(VisibilityCompetitor).where(VisibilityCompetitor.tenant_id == tenant_id).order_by(VisibilityCompetitor.created_at.desc()).limit(100)).all()
    return {"items": [{"id": r.id, "name": r.name, "domain": r.domain, "notes": r.notes, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}

@router.post("/competitors", status_code=201)
def add_competitor(tenant_id: str, payload: CompetitorPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = VisibilityCompetitor(tenant_id=tenant_id, name=payload.name.strip(), domain=_domain(payload.domain), notes=payload.notes.strip())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "domain": row.domain, "notes": row.notes}

@router.delete("/competitors/{competitor_id}")
def delete_competitor(tenant_id: str, competitor_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = db.scalar(select(VisibilityCompetitor).where(VisibilityCompetitor.id == competitor_id, VisibilityCompetitor.tenant_id == tenant_id))
    if not row:
        raise HTTPException(404, "Competitor not found")
    db.delete(row); db.commit()
    return {"deleted": True}

@router.get("/queries")
def list_queries(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    rows = db.scalars(select(VisibilityQuery).where(VisibilityQuery.tenant_id == tenant_id).order_by(VisibilityQuery.created_at.desc()).limit(200)).all()
    return {"items": [{"id": r.id, "query_text": r.query_text, "intent": r.intent, "locale": r.locale, "topic": r.topic, "is_active": r.is_active, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}

@router.post("/queries", status_code=201)
def add_query(tenant_id: str, payload: QueryPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = VisibilityQuery(tenant_id=tenant_id, query_text=payload.query_text.strip(), intent=payload.intent, locale=payload.locale.strip(), topic=payload.topic.strip(), is_active=payload.is_active)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "query_text": row.query_text, "intent": row.intent, "locale": row.locale, "topic": row.topic, "is_active": row.is_active}
