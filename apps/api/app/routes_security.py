"""Authenticated tenant-scoped visitor workflows."""
import hashlib, json, secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt
from .db import SessionLocal
from .config import settings
from .models import User, Tenant
from .models_security import SecuritySite, VisitorPass, VisitorEvent

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/security", tags=["security-visitor-management"])

def db_session():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def principal(authorization: str | None = Header(default=None), db: Session = Depends(db_session)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token required")
    try: payload = jwt.decode(authorization.split(" ",1)[1], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError: raise HTTPException(401, "Invalid access token")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active: raise HTTPException(401, "Active user required")
    return user

def tenant_access(tenant_id: str, user: User, db: Session):
    if user.tenant_id != tenant_id:
        raise HTTPException(403, "Tenant access denied")
    tenant = db.get(Tenant, tenant_id)
    if not tenant or str(tenant.status).lower() not in ("active", "trial", "pending"):
        raise HTTPException(404, "Tenant not found or inactive")

def admin_only(user: User):
    if str(user.role).lower() not in ("owner", "admin", "tenant_admin", "manager", "security_admin"):
        raise HTTPException(403, "Administrator permission required")

class SiteInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    industry: str = Field(default="apartment", pattern="^(school|apartment|hospital)$")

class PassInput(BaseModel):
    visitor_name: str = Field(min_length=1, max_length=160)
    visitor_mobile: str = Field(default="", max_length=32)
    purpose: str = Field(default="", max_length=240)
    destination: str = Field(default="", max_length=240)
    vehicle_number: str = Field(default="", max_length=40)
    site_id: str | None = None
    needs_approval: bool = True
    valid_hours: int = Field(default=24, ge=1, le=168)

def event(db, tenant_id, pass_id, actor_id, kind, details=None):
    db.add(VisitorEvent(tenant_id=tenant_id, pass_id=pass_id, actor_id=actor_id, event_type=kind, details_json=json.dumps(details or {})))

def pass_json(p, token=None):
    return {"id":p.id,"tenant_id":p.tenant_id,"site_id":p.site_id,"visitor_name":p.visitor_name,"visitor_mobile":p.visitor_mobile,"purpose":p.purpose,"destination":p.destination,"vehicle_number":p.vehicle_number,"industry":p.industry,"status":p.status,"expires_at":p.expires_at.isoformat() if p.expires_at else None,"created_at":p.created_at.isoformat() if p.created_at else None,"checked_in_at":p.checked_in_at.isoformat() if p.checked_in_at else None,"checked_out_at":p.checked_out_at.isoformat() if p.checked_out_at else None,"qr_token":token}

@router.get("/sites")
def list_sites(tenant_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id,user,db)
    rows=db.scalars(select(SecuritySite).where(SecuritySite.tenant_id==tenant_id).order_by(SecuritySite.created_at.desc())).all()
    return {"items":[{"id":s.id,"name":s.name,"industry":s.industry,"enabled":s.enabled,"settings":json.loads(s.settings_json or "{}")} for s in rows]}

@router.post("/sites")
def create_site(tenant_id: str, body: SiteInput, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id,user,db); admin_only(user)
    s=SecuritySite(tenant_id=tenant_id,name=body.name.strip(),industry=body.industry)
    db.add(s); db.commit(); db.refresh(s)
    return {"id":s.id,"name":s.name,"industry":s.industry,"enabled":s.enabled}

@router.get("/passes")
def list_passes(tenant_id: str, user: User = Depends(principal), db: Session = Depends(db_session), status: str | None = None, limit: int = 100):
    tenant_access(tenant_id,user,db)
    q=select(VisitorPass).where(VisitorPass.tenant_id==tenant_id).order_by(VisitorPass.created_at.desc()).limit(max(1,min(limit,200)))
    if status: q=q.where(VisitorPass.status==status)
    return {"items":[pass_json(p) for p in db.scalars(q).all()]}

@router.post("/passes")
def create_pass(tenant_id: str, body: PassInput, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id,user,db)
    if body.site_id and not db.scalar(select(SecuritySite).where(SecuritySite.id==body.site_id,SecuritySite.tenant_id==tenant_id)):
        raise HTTPException(404,"Site not found")
    raw=secrets.token_urlsafe(32); now=datetime.utcnow()
    p=VisitorPass(tenant_id=tenant_id,site_id=body.site_id,token_hash=hashlib.sha256(raw.encode()).hexdigest(),visitor_name=body.visitor_name.strip(),visitor_mobile=body.visitor_mobile,purpose=body.purpose,destination=body.destination,vehicle_number=body.vehicle_number,industry=(db.get(SecuritySite,body.site_id).industry if body.site_id else "apartment"),status="pending" if body.needs_approval else "approved",expires_at=now+timedelta(hours=body.valid_hours),created_by=user.id,approved_by=(None if body.needs_approval else user.id))
    db.add(p); db.flush(); event(db,tenant_id,p.id,user.id,"pass_created",{"status":p.status}); db.commit(); db.refresh(p)
    return pass_json(p,raw)

@router.post("/passes/{pass_id}/approve")
def approve_pass(tenant_id: str, pass_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id,user,db); admin_only(user)
    p=db.scalar(select(VisitorPass).where(VisitorPass.id==pass_id,VisitorPass.tenant_id==tenant_id))
    if not p: raise HTTPException(404,"Pass not found")
    if p.status!="pending": raise HTTPException(409,"Only pending passes can be approved")
    if p.expires_at and p.expires_at<datetime.utcnow(): p.status="expired"
    else: p.status="approved"; p.approved_by=user.id
    event(db,tenant_id,p.id,user.id,"approval_decided",{"status":p.status}); db.commit(); db.refresh(p)
    return pass_json(p)

@router.post("/passes/{pass_id}/check-in")
def check_in(tenant_id: str, pass_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id,user,db)
    p=db.scalar(select(VisitorPass).where(VisitorPass.id==pass_id,VisitorPass.tenant_id==tenant_id))
    if not p: raise HTTPException(404,"Pass not found")
    if p.status!="approved": raise HTTPException(409,"Pass must be approved before entry")
    if p.expires_at and p.expires_at<datetime.utcnow(): p.status="expired"; db.commit(); raise HTTPException(410,"Pass expired")
    p.status="checked_in"; p.checked_in_at=datetime.utcnow(); event(db,tenant_id,p.id,user.id,"visitor_checked_in"); db.commit(); db.refresh(p)
    return pass_json(p)

@router.post("/passes/{pass_id}/check-out")
def check_out(tenant_id: str, pass_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id,user,db)
    p=db.scalar(select(VisitorPass).where(VisitorPass.id==pass_id,VisitorPass.tenant_id==tenant_id))
    if not p: raise HTTPException(404,"Pass not found")
    if p.status!="checked_in": raise HTTPException(409,"Only checked-in visitors can check out")
    p.status="checked_out"; p.checked_out_at=datetime.utcnow(); event(db,tenant_id,p.id,user.id,"visitor_checked_out"); db.commit(); db.refresh(p)
    return pass_json(p)

@router.get("/events")
def list_events(tenant_id: str, user: User = Depends(principal), db: Session = Depends(db_session), limit: int = 200):
    tenant_access(tenant_id,user,db)
    rows=db.scalars(select(VisitorEvent).where(VisitorEvent.tenant_id==tenant_id).order_by(VisitorEvent.created_at.desc()).limit(max(1,min(limit,500)))).all()
    return {"items":[{"id":e.id,"pass_id":e.pass_id,"event_type":e.event_type,"actor_id":e.actor_id,"details":json.loads(e.details_json or "{}"),"created_at":e.created_at.isoformat()} for e in rows]}
