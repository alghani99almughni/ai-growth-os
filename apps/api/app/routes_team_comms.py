from datetime import datetime
from uuid import uuid4
import csv, io
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, Text, DateTime, ForeignKey, select
from sqlalchemy.orm import Session, Mapped, mapped_column
import jwt
from .db import Base, SessionLocal
from .config import settings
from .models import User

router = APIRouter(prefix="/api/v1/team-comms", tags=["team-comms"])

class TeamMessage(Base):
    __tablename__ = "team_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    sender_id: Mapped[str] = mapped_column(String(36), index=True)
    sender_name: Mapped[str] = mapped_column(String(160), default="")
    recipient_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    room: Mapped[str] = mapped_column(String(160), default="team", index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    recipient_id: str | None = None
    room: str = Field(default="team", min_length=1, max_length=160)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def actor(authorization: str | None, db: Session):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    try:
        claims = jwt.decode(authorization.split(" ",1)[1], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except Exception:
        raise HTTPException(401, "Invalid access token")
    user = db.get(User, claims.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(401, "Inactive user")
    return user

@router.get("/users")
def team_users(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db)
    users = db.scalars(select(User).where(User.tenant_id == user.tenant_id, User.is_active == True).order_by(User.name)).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role} for u in users]

@router.get("/messages")
def list_messages(room: str = "team", limit: int = Query(default=100, ge=1, le=500), authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db)
    rows = db.scalars(select(TeamMessage).where(
        TeamMessage.tenant_id == user.tenant_id,
        TeamMessage.room == room,
        ((TeamMessage.recipient_id == None) | (TeamMessage.recipient_id == user.id) | (TeamMessage.sender_id == user.id))
    ).order_by(TeamMessage.created_at.desc()).limit(limit)).all()
    return [{"id": m.id, "sender_id": m.sender_id, "sender_name": m.sender_name, "recipient_id": m.recipient_id, "room": m.room, "message": m.message, "created_at": m.created_at.isoformat() + "Z"} for m in reversed(rows)]

@router.post("/messages")
def send_message(payload: MessageIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db)
    if payload.recipient_id:
        target = db.get(User, payload.recipient_id)
        if not target or target.tenant_id != user.tenant_id or not target.is_active:
            raise HTTPException(404, "Recipient not found in this workspace")
    row = TeamMessage(tenant_id=user.tenant_id, sender_id=user.id, sender_name=user.name, recipient_id=payload.recipient_id, room=payload.room.strip(), message=payload.message.strip())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "sender_id": row.sender_id, "sender_name": row.sender_name, "recipient_id": row.recipient_id, "room": row.room, "message": row.message, "created_at": row.created_at.isoformat() + "Z"}

@router.get("/export.csv")
def export_messages(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db)
    if user.role not in {"owner", "tenant_admin", "admin", "manager", "security_manager", "platform_admin", "super_admin"}:
        raise HTTPException(403, "Export permission required")
    rows = db.scalars(select(TeamMessage).where(TeamMessage.tenant_id == user.tenant_id).order_by(TeamMessage.created_at)).all()
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(["timestamp_utc", "room", "sender", "sender_id", "recipient_id", "message"])
    for m in rows: writer.writerow([m.created_at.isoformat() + "Z", m.room, m.sender_name, m.sender_id, m.recipient_id or "", m.message])
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=team-chat-export.csv"})
