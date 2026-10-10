"""Managed global industry catalogue for AI Growth OS.

Super-admins manage category/business-type entries and default role suggestions.
Tenant selection is stored separately from global templates so catalogue edits never
silently overwrite a tenant's configuration.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, Session

from .db import Base, SessionLocal
from .models import Tenant, User
from .models_growth import TenantSetting
from .config import settings
from .security import decode_token_strict

router = APIRouter()
security = HTTPBearer(auto_error=False)


class IndustryCatalogEntry(Base):
    __tablename__ = "industry_catalog_entries"
    __table_args__ = (UniqueConstraint("category", "business_type", name="uq_industry_catalog_category_business_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category: Mapped[str] = mapped_column(String(160), index=True)
    business_type: Mapped[str] = mapped_column(String(200))
    roles_json: Mapped[str] = mapped_column(Text, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


DEFAULT_CATALOG = [
    ("Hospitality & Food Services", "Hotels & Fine Dining", "Hotel Manager, Receptionist, Concierge, Housekeeper, Head Chef, Sous Chef, Line Cook, Waiter/Waitress, Cashier, Bartender, Sommelier, Valet Parking Staff"),
    ("Hospitality & Food Services", "Small Eateries, Cafes & Bakeries", "Cafe Manager, Barista, Head Baker, Pastry Chef, Cashier, Counter Service Staff, Kitchen Porter / Dishwasher, Delivery Driver"),
    ("Healthcare & Wellness", "Hospitals & Major Medical Centers", "Medical Director, Physician / Specialist Doctor, Registered Nurse (RN), Pharmacist, Clinical Lab Technician, Radiologist, Medical Records Clerk, Billing & Coding Specialist"),
    ("Healthcare & Wellness", "Small Clinics, Dental & Diagnostics", "Clinic Manager, General Practitioner (GP), Dentist, Dental Assistant, Clinic Receptionist, Phlebotomist, Medical Assistant, Clinic Sanitation Staff"),
    ("Personal Care & Beauty", "Salons, Spas & Barbershops", "Salon Owner / Manager, Senior Hair Stylist, Barber, Esthetician / Skin Specialist, Nail Technician, Massage Therapist, Front Desk Receptionist, Salon Assistant"),
    ("Fitness & Recreation", "Gyms, Yoga Studios & Sports Centers", "Gym Manager, Personal Trainer, Fitness Instructor, Yoga / Pilates Instructor, Front Desk Agent, Equipment Maintenance Technician, Locker Room Attendant"),
    ("Retail & Consumer Goods", "Supermarkets & Retail Stores", "Store Manager, Assistant Store Manager, Sales Associate, Cashier, Stocker / Inventory Clerk, Visual Merchandiser, Customer Service Representative"),
    ("Retail & Consumer Goods", "Small Boutiques & Specialty Shops", "Boutique Owner, Shop Assistant, Cashier, Tailor / Alterations Specialist, E-Commerce Order Fulfillment Specialist"),
    ("Automotive Services", "Auto Repair Shops, Garages & Dealerships", "Workshop Manager, Auto Mechanic, Diagnostic Technician, Auto Electrician, Service Advisor, Parts Counter Clerk, Auto Detailer / Car Washer"),
    ("Information Technology (IT)", "Software, Cloud & IT Services", "Software Engineer, QA / Automation Tester, IT Support / Helpdesk Specialist, DevOps & Cloud Engineer, Product Manager, UI/UX Designer, Cybersecurity Analyst, Data Scientist"),
    ("Finance & Professional Services", "Banks, Accounting & Tax Firms", "Branch Manager, Bank Teller, Loan / Credit Officer, Accountant, Financial Auditor, Tax Specialist, Wealth Advisor / Financial Planner"),
    ("Manufacturing & Production", "Factories & Assembly Plants", "Plant Manager, Production Line Operator, Quality Control (QC) Inspector, Maintenance Engineer, Warehouse Supervisor, Environmental Health & Safety (EHS) Officer"),
    ("Construction & Skilled Trades", "Construction, Contracting & Maintenance", "Project Manager, Site Engineer, Architect, Quantity Surveyor, Electrician, Plumber, Carpenter, Painter, Mason, Safety Officer"),
    ("Education & Childcare", "Schools, Universities & Daycare Centers", "School Principal, Teacher / Professor, Teaching Assistant, Daycare Provider / Nanny, School Administrator, Academic Counselor, Librarian"),
    ("Professional & Creative Services", "Legal, Real Estate & Agencies", "Managing Partner, Attorney / Lawyer, Paralegal, Real Estate Agent, Property Manager, Graphic Designer, Copywriter, Digital Marketing Specialist"),
    ("Logistics & Transportation", "Warehousing, Courier & Transport", "Fleet Manager, Warehouse Associate, Dispatcher, Logistics Coordinator, Delivery Driver, Forklift Operator, Freight Clerk"),
    ("Human Resources & Administration", "Corporate Office Services", "HR Manager, Talent Acquisition Specialist, Payroll Administrator, Office Manager, Executive Assistant, Facilities Coordinator"),
    ("Agriculture & Agribusiness", "Farms, Nurseries & Agricultural Produce", "Farm Manager, Agronomist, Crop Worker, Livestock Caretaker, Heavy Equipment Operator, Supply Chain Coordinator"),
]


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security), db: Session = Depends(_db)):
    if not credentials:
        raise HTTPException(401, "Authentication required")
    try:
        claims = decode_token_strict(credentials.credentials, settings.jwt_secret, settings.jwt_algorithm)
        uid = claims.get("sub")
    except ValueError as exc:
        raise HTTPException(401, str(exc))
    user = db.get(User, uid)
    if not user or not user.is_active or claims.get("tenant_id") != user.tenant_id:
        raise HTTPException(401, "Invalid tenant context")
    return user


def _platform_admin(user=Depends(_current_user)):
    if user.role not in ("platform_admin", "super_admin"):
        raise HTTPException(403, "Platform admin access required")
    return user


def _seed(db: Session):
    if db.scalar(select(IndustryCatalogEntry.id).limit(1)):
        return
    for i, (category, business_type, roles) in enumerate(DEFAULT_CATALOG, start=1):
        db.add(IndustryCatalogEntry(category=category, business_type=business_type,
                                    roles_json=json.dumps([x.strip() for x in roles.split(",")]),
                                    sort_order=i * 10, is_active=True))
    db.commit()


def _out(row: IndustryCatalogEntry):
    try:
        roles = json.loads(row.roles_json or "[]")
    except Exception:
        roles = []
    return {"id": row.id, "category": row.category, "business_type": row.business_type,
            "roles": roles, "is_active": row.is_active, "sort_order": row.sort_order,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


class CatalogPayload(BaseModel):
    category: str = Field(min_length=2, max_length=160)
    business_type: str = Field(min_length=2, max_length=200)
    roles: list[str] = Field(default_factory=list, max_length=200)
    is_active: bool = True
    sort_order: int = Field(default=100, ge=0, le=100000)


class TenantIndustrySelection(BaseModel):
    catalog_entry_id: str = Field(min_length=1, max_length=36)
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/api/v1/public/industry-catalog")
def public_industry_catalog(db: Session = Depends(_db)):
    _seed(db)
    rows = db.scalars(select(IndustryCatalogEntry).where(IndustryCatalogEntry.is_active.is_(True))
                      .order_by(IndustryCatalogEntry.sort_order, IndustryCatalogEntry.category,
                                IndustryCatalogEntry.business_type)).all()
    return {"items": [_out(x) for x in rows]}


@router.get("/api/v1/platform/industry-catalog")
def admin_industry_catalog(include_inactive: bool = True, db: Session = Depends(_db), user=Depends(_platform_admin)):
    _seed(db)
    query = select(IndustryCatalogEntry)
    if not include_inactive:
        query = query.where(IndustryCatalogEntry.is_active.is_(True))
    rows = db.scalars(query.order_by(IndustryCatalogEntry.sort_order, IndustryCatalogEntry.category,
                                     IndustryCatalogEntry.business_type)).all()
    return {"items": [_out(x) for x in rows]}


@router.post("/api/v1/platform/industry-catalog", status_code=201)
def add_catalog_entry(payload: CatalogPayload, db: Session = Depends(_db), user=Depends(_platform_admin)):
    _seed(db)
    category, business_type = payload.category.strip(), payload.business_type.strip()
    existing = db.scalar(select(IndustryCatalogEntry).where(
        IndustryCatalogEntry.category == category, IndustryCatalogEntry.business_type == business_type))
    if existing:
        raise HTTPException(409, "This business type already exists under the selected category")
    row = IndustryCatalogEntry(category=category, business_type=business_type,
        roles_json=json.dumps([x.strip() for x in payload.roles if x.strip()]),
        is_active=payload.is_active, sort_order=payload.sort_order)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.patch("/api/v1/platform/industry-catalog/{entry_id}")
def update_catalog_entry(entry_id: str, payload: CatalogPayload, db: Session = Depends(_db), user=Depends(_platform_admin)):
    row = db.get(IndustryCatalogEntry, entry_id)
    if not row:
        raise HTTPException(404, "Industry catalogue entry not found")
    duplicate = db.scalar(select(IndustryCatalogEntry).where(
        IndustryCatalogEntry.category == payload.category.strip(),
        IndustryCatalogEntry.business_type == payload.business_type.strip(),
        IndustryCatalogEntry.id != entry_id))
    if duplicate:
        raise HTTPException(409, "This business type already exists under the selected category")
    row.category = payload.category.strip()
    row.business_type = payload.business_type.strip()
    row.roles_json = json.dumps([x.strip() for x in payload.roles if x.strip()])
    row.is_active = payload.is_active
    row.sort_order = payload.sort_order
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/api/v1/platform/industry-catalog/{entry_id}")
def disable_catalog_entry(entry_id: str, db: Session = Depends(_db), user=Depends(_platform_admin)):
    row = db.get(IndustryCatalogEntry, entry_id)
    if not row:
        raise HTTPException(404, "Industry catalogue entry not found")
    # Soft-disable: historical tenants remain intact and references are not deleted.
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "id": row.id, "is_active": False}


@router.put("/api/v1/tenants/{tenant_id}/industry-selection")
def set_tenant_industry_selection(tenant_id: str, payload: TenantIndustrySelection,
                                  db: Session = Depends(_db), user=Depends(_current_user)):
    if user.role not in ("platform_admin", "super_admin") and user.tenant_id != tenant_id:
        raise HTTPException(403, "Tenant access denied")
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    entry = db.get(IndustryCatalogEntry, payload.catalog_entry_id)
    if not entry or not entry.is_active:
        raise HTTPException(404, "Active industry catalogue entry not found")
    selection = {"catalog_entry_id": entry.id, "category": entry.category,
                 "business_type": entry.business_type, "roles": json.loads(entry.roles_json or "[]"),
                 "notes": payload.notes}
    row = db.scalar(select(TenantSetting).where(TenantSetting.tenant_id == tenant_id,
                                               TenantSetting.key == "industry_selection"))
    if not row:
        row = TenantSetting(tenant_id=tenant_id, key="industry_selection", value_json=json.dumps(selection))
        db.add(row)
    else:
        row.value_json = json.dumps(selection)
    db.commit()
    return {"ok": True, "tenant_id": tenant_id, "selection": selection}


@router.get("/api/v1/tenants/{tenant_id}/industry-selection")
def get_tenant_industry_selection(tenant_id: str, db: Session = Depends(_db), user=Depends(_current_user)):
    if user.role not in ("platform_admin", "super_admin") and user.tenant_id != tenant_id:
        raise HTTPException(403, "Tenant access denied")
    row = db.scalar(select(TenantSetting).where(TenantSetting.tenant_id == tenant_id,
                                               TenantSetting.key == "industry_selection"))
    return {"tenant_id": tenant_id, "selection": json.loads(row.value_json) if row else None}
