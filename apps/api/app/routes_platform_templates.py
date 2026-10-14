"""Super-admin management API for platform inbox reply templates."""
from __future__ import annotations
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .db import SessionLocal
from .models import User
from .models_platform_templates import PlatformReplyTemplate
from .security import decode_token_strict, audit

router = APIRouter()
bearer = HTTPBearer(auto_error=False)

def db_dep():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(db_dep)):
    if not creds: raise HTTPException(401, "Authentication required")
    try: claims = decode_token_strict(creds.credentials, settings.jwt_secret, settings.jwt_algorithm)
    except ValueError as exc: raise HTTPException(401, str(exc))
    user = db.get(User, claims.get("sub"))
    if not user or not user.is_active: raise HTTPException(401, "Invalid user")
    if user.role not in ("platform_admin", "super_admin"): raise HTTPException(403, "Platform admin access required")
    return user

class TemplatePayload(BaseModel):
    channel: str = Field(pattern="^(email|whatsapp)$")
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    keywords: str = Field(default="", max_length=1000)
    is_active: bool = True
    auto_reply: bool = False

@router.get("/api/v1/platform/communications/templates")
def list_templates(channel: str | None = None, user=Depends(admin), db: Session = Depends(db_dep)):
    q = select(PlatformReplyTemplate)
    if channel:
        if channel not in ("email", "whatsapp"): raise HTTPException(400, "channel must be email or whatsapp")
        q = q.where(PlatformReplyTemplate.channel == channel)
    rows = db.scalars(q.order_by(PlatformReplyTemplate.channel, PlatformReplyTemplate.name)).all()
    return {"items":[{"id":r.id,"channel":r.channel,"name":r.name,"subject":r.subject,"body":r.body,"keywords":r.keywords,"is_active":r.is_active,"auto_reply":r.auto_reply,"updated_at":r.updated_at.isoformat() if r.updated_at else None} for r in rows]}

@router.post("/api/v1/platform/communications/templates")
def create_template(payload: TemplatePayload, user=Depends(admin), db: Session=Depends(db_dep)):
    row=PlatformReplyTemplate(id=str(uuid.uuid4()), **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    try: audit(db, tenant_id=None, actor_id=user.id, action="platform.reply_template_created", target_type="platform_reply_template", target_id=row.id, detail={"channel":row.channel,"auto_reply":row.auto_reply})
    except Exception: pass
    return {"id":row.id,"created":True}

@router.put("/api/v1/platform/communications/templates/{template_id}")
def update_template(template_id: str, payload: TemplatePayload, user=Depends(admin), db: Session=Depends(db_dep)):
    row=db.get(PlatformReplyTemplate, template_id)
    if not row: raise HTTPException(404,"Template not found")
    for key,value in payload.model_dump().items(): setattr(row,key,value)
    row.updated_at=datetime.utcnow(); db.commit()
    return {"id":row.id,"updated":True}

@router.delete("/api/v1/platform/communications/templates/{template_id}")
def delete_template(template_id: str, user=Depends(admin), db: Session=Depends(db_dep)):
    row=db.get(PlatformReplyTemplate,template_id)
    if not row: raise HTTPException(404,"Template not found")
    db.delete(row); db.commit()
    return {"id":template_id,"deleted":True}

def choose_template(db: Session, channel: str, message: str, subject: str = ""):
    """Return a deterministic active auto-reply template only when one is explicitly enabled."""
    rows=db.scalars(select(PlatformReplyTemplate).where(
        PlatformReplyTemplate.channel==channel,
        PlatformReplyTemplate.is_active.is_(True),
        PlatformReplyTemplate.auto_reply.is_(True)
    ).order_by(PlatformReplyTemplate.updated_at.desc())).all()
    haystack=(subject+" "+message).lower()
    fallback=None
    for row in rows:
        terms=[x.strip().lower() for x in (row.keywords or "").split(",") if x.strip()]
        if not terms: fallback = fallback or row
        elif any(term in haystack for term in terms): return row
    return fallback
