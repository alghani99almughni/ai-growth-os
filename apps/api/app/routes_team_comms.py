from datetime import datetime
from uuid import uuid4
import base64, csv, io, re, json
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, Text, DateTime, Boolean, LargeBinary, ForeignKey, select
from sqlalchemy.orm import Session, Mapped, mapped_column
import jwt
from .db import Base, SessionLocal
from .config import settings
from .models import User
from .models_ai import StaffMember, Department, RoleDefinition

router = APIRouter(prefix="/api/v1/team-comms", tags=["team-comms"])
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf", "text/plain", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"}

class TeamMessage(Base):
    __tablename__ = "team_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    sender_id: Mapped[str] = mapped_column(String(36), index=True)
    sender_name: Mapped[str] = mapped_column(String(160), default="")
    recipient_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    room: Mapped[str] = mapped_column(String(160), default="team", index=True)
    message: Mapped[str] = mapped_column(Text)
    formatting: Mapped[str] = mapped_column(String(40), default="plain")
    attachment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class TeamRoom(Base):
    __tablename__ = "team_comms_rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    room_key: Mapped[str] = mapped_column(String(160), index=True)
    name: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TeamRoomMember(Base):
    __tablename__ = "team_comms_room_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    room_key: Mapped[str] = mapped_column(String(160), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    added_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TeamAttachment(Base):
    __tablename__ = "team_comms_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    uploaded_by: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column()
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TeamCommsAccess(Base):
    __tablename__ = "team_comms_access"
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class TeamCommsPreference(Base):
    __tablename__ = "team_comms_preferences"
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ringtone: Mapped[str] = mapped_column(String(30), default="classic")
    accent_color: Mapped[str] = mapped_column(String(20), default="#293dbd")
    chat_background: Mapped[str] = mapped_column(String(20), default="#fbfcfe")

class MessageIn(BaseModel):
    message: str = Field(default="", max_length=10000)
    recipient_id: str | None = None
    room: str = Field(default="team", min_length=1, max_length=160)
    formatting: str = Field(default="plain", pattern="^(plain|bold|underline|red|bold_red|underline_red)$")
    attachment_id: str | None = None

class RoomCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    member_ids: list[str] = Field(default_factory=list, max_length=100)

class AttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    data_base64: str = Field(min_length=1, max_length=12_000_000)

class PreferenceIn(BaseModel):
    notifications_enabled: bool = True
    ringtone: str = Field(default="classic", pattern="^(classic|gentle|urgent|silent)$")
    accent_color: str = Field(default="#293dbd", pattern="^#[0-9a-fA-F]{6}$")
    chat_background: str = Field(default="#fbfcfe", pattern="^#[0-9a-fA-F]{6}$")

class AccessIn(BaseModel):
    enabled: bool

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
    access = db.get(TeamCommsAccess, user.id)
    if access and (access.tenant_id != user.tenant_id or not access.enabled):
        raise HTTPException(403, "Team chat is disabled for this member")
    return user

def require_permission(user: User, db: Session, permission: str):
    if user.role in {"owner", "tenant_admin", "admin", "platform_admin", "super_admin"}:
        return
    role = db.scalar(select(RoleDefinition).where(RoleDefinition.tenant_id == user.tenant_id, RoleDefinition.name == user.role))
    try:
        permissions = json.loads(role.permissions_json or "[]") if role else []
    except Exception:
        permissions = []
    if permission not in permissions and "*" not in permissions:
        raise HTTPException(403, "Role permission required: " + permission)

def require_admin(user: User, db: Session):
    require_permission(user, db, "team.manage")

def message_json(m):
    return {"id":m.id,"sender_id":m.sender_id,"sender_name":m.sender_name,"recipient_id":m.recipient_id,"room":m.room,"message":m.message,"formatting":m.formatting,"attachment_id":m.attachment_id,"created_at":m.created_at.isoformat()+"Z"}

@router.get("/users")
def team_users(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db); require_permission(user, db, "communications.view")
    users = db.scalars(select(User).where(User.tenant_id == user.tenant_id, User.is_active == True).order_by(User.name)).all()
    staff = db.scalars(select(StaffMember).where(StaffMember.tenant_id == user.tenant_id, StaffMember.is_active == True)).all()
    departments = {d.id:d.name for d in db.scalars(select(Department).where(Department.tenant_id == user.tenant_id)).all()}
    staff_by_user = {s.user_id:s for s in staff if s.user_id}
    access_rows = db.scalars(select(TeamCommsAccess).where(TeamCommsAccess.tenant_id == user.tenant_id)).all()
    access_by_user = {a.user_id:a.enabled for a in access_rows}
    return [{"id":u.id,"name":u.name,"email":u.email,"role":u.role,"department_id":getattr(staff_by_user.get(u.id),"department_id",None),"department_name":departments.get(getattr(staff_by_user.get(u.id),"department_id",None),"Unassigned"),"chat_enabled":access_by_user.get(u.id,True)} for u in users]

@router.patch("/users/{target_id}/access")
def set_chat_access(target_id: str, payload: AccessIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db); require_admin(user, db)
    target = db.get(User, target_id)
    if not target or target.tenant_id != user.tenant_id:
        raise HTTPException(404, "Member not found in this workspace")
    row = db.get(TeamCommsAccess, target.id)
    if not row:
        row = TeamCommsAccess(user_id=target.id, tenant_id=user.tenant_id, enabled=payload.enabled); db.add(row)
    else:
        row.enabled = payload.enabled
    db.commit()
    return {"user_id":target.id,"chat_enabled":row.enabled}

@router.get("/preferences")
def get_preferences(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user=actor(authorization,db); require_permission(user, db, "communications.view"); row=db.get(TeamCommsPreference,user.id)
    return {"notifications_enabled":row.notifications_enabled if row else True,"ringtone":row.ringtone if row else "classic","accent_color":row.accent_color if row else "#293dbd","chat_background":row.chat_background if row else "#fbfcfe"}

@router.put("/preferences")
def save_preferences(payload: PreferenceIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user=actor(authorization,db); require_permission(user, db, "communications.view"); row=db.get(TeamCommsPreference,user.id)
    if not row:
        row=TeamCommsPreference(user_id=user.id,tenant_id=user.tenant_id); db.add(row)
    row.notifications_enabled=payload.notifications_enabled; row.ringtone=payload.ringtone; row.accent_color=payload.accent_color; row.chat_background=payload.chat_background
    db.commit()
    return {"ok":True,"notifications_enabled":row.notifications_enabled,"ringtone":row.ringtone,"accent_color":row.accent_color,"chat_background":row.chat_background}

@router.get("/rooms")
def list_rooms(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db); require_permission(user, db, "communications.view")
    memberships = db.scalars(select(TeamRoomMember).where(TeamRoomMember.tenant_id == user.tenant_id,
        TeamRoomMember.user_id == user.id)).all()
    keys = {m.room_key for m in memberships}
    rooms = db.scalars(select(TeamRoom).where(TeamRoom.tenant_id == user.tenant_id).order_by(TeamRoom.name)).all()
    return {"items":[{"room":r.room_key,"name":r.name,"created_by":r.created_by,"member_count":
        len(db.scalars(select(TeamRoomMember).where(TeamRoomMember.tenant_id==user.tenant_id,
        TeamRoomMember.room_key==r.room_key)).all())} for r in rooms if r.room_key in keys]}

@router.post("/rooms", status_code=201)
def create_room(payload: RoomCreateIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db); require_permission(user, db, "communications.reply")
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "Room name is required")
    # Stable URL-safe-ish room key; room names cannot collide within a tenant.
    key = "grp-" + str(uuid4())
    ids = set(payload.member_ids); ids.add(user.id)
    users = db.scalars(select(User).where(User.tenant_id==user.tenant_id, User.is_active==True,
        User.id.in_(ids))).all() if ids else []
    if {u.id for u in users} != ids:
        raise HTTPException(400, "All room members must be active users in this workspace")
    disabled = db.scalars(select(TeamCommsAccess).where(TeamCommsAccess.tenant_id==user.tenant_id,
        TeamCommsAccess.user_id.in_(ids), TeamCommsAccess.enabled==False)).all()
    if disabled:
        raise HTTPException(400, "A selected member has team communications disabled")
    room = TeamRoom(tenant_id=user.tenant_id, room_key=key, name=name, created_by=user.id)
    db.add(room)
    for uid in ids:
        db.add(TeamRoomMember(tenant_id=user.tenant_id, room_key=key, user_id=uid, added_by=user.id))
    db.commit()
    return {"room":key,"name":name,"member_ids":sorted(ids),"created_by":user.id}

@router.get("/messages")
def list_messages(room: str = "team", limit: int = Query(default=100, ge=1, le=500), authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db); require_permission(user, db, "communications.view")
    if room != "team":
        membership = db.scalar(select(TeamRoomMember).where(TeamRoomMember.tenant_id==user.tenant_id, TeamRoomMember.room_key==room, TeamRoomMember.user_id==user.id))
        exists = db.scalar(select(TeamRoom.id).where(TeamRoom.tenant_id==user.tenant_id, TeamRoom.room_key==room))
        if not membership or not exists:
            raise HTTPException(404, "Room not found")
    rows = db.scalars(select(TeamMessage).where(TeamMessage.tenant_id == user.tenant_id, TeamMessage.room == room, ((TeamMessage.recipient_id == None) | (TeamMessage.recipient_id == user.id) | (TeamMessage.sender_id == user.id))).order_by(TeamMessage.created_at.desc()).limit(limit)).all()
    return [message_json(m) for m in reversed(rows)]

@router.post("/attachments")
def upload_attachment(payload: AttachmentIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user=actor(authorization,db); require_permission(user, db, "communications.reply")
    content_type=payload.content_type.lower().split(";")[0].strip()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(415,"This file type is not allowed")
    try: raw=base64.b64decode(payload.data_base64,validate=True)
    except Exception: raise HTTPException(400,"Invalid file encoding")
    if not raw or len(raw)>MAX_ATTACHMENT_BYTES:
        raise HTTPException(413,"Files must be 8 MB or smaller")
    filename=re.sub(r"[^a-zA-Z0-9._ ()-]","_",payload.filename).strip()[:255] or "attachment"
    row=TeamAttachment(tenant_id=user.tenant_id,uploaded_by=user.id,filename=filename,content_type=content_type,size_bytes=len(raw),content=raw)
    db.add(row);db.commit();db.refresh(row)
    return {"id":row.id,"filename":row.filename,"content_type":row.content_type,"size_bytes":row.size_bytes}

@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user=actor(authorization,db); require_permission(user, db, "communications.view")
    row=db.get(TeamAttachment,attachment_id)
    if not row or row.tenant_id!=user.tenant_id:
        raise HTTPException(404,"Attachment not found")
    return StreamingResponse(io.BytesIO(row.content),media_type=row.content_type,headers={"Content-Disposition":f'inline; filename="{row.filename.replace(chr(34), "")}"',"X-Content-Type-Options":"nosniff"})

@router.post("/messages")
def send_message(payload: MessageIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db); require_permission(user, db, "communications.reply")
    if not payload.message.strip() and not payload.attachment_id:
        raise HTTPException(422,"Add a message or attachment")
    room_key = payload.room.strip()
    if room_key != "team":
        membership = db.scalar(select(TeamRoomMember).where(TeamRoomMember.tenant_id==user.tenant_id, TeamRoomMember.room_key==room_key, TeamRoomMember.user_id==user.id))
        exists = db.scalar(select(TeamRoom.id).where(TeamRoom.tenant_id==user.tenant_id, TeamRoom.room_key==room_key))
        if not membership or not exists:
            raise HTTPException(404, "Room not found")
    if payload.recipient_id:
        target = db.get(User, payload.recipient_id)
        if not target or target.tenant_id != user.tenant_id or not target.is_active:
            raise HTTPException(404, "Recipient not found in this workspace")
        access=db.get(TeamCommsAccess,target.id)
        if access and not access.enabled: raise HTTPException(403,"Recipient has team chat disabled")
    attachment_id=None
    if payload.attachment_id:
        attachment=db.get(TeamAttachment,payload.attachment_id)
        if not attachment or attachment.tenant_id!=user.tenant_id or attachment.uploaded_by!=user.id:
            raise HTTPException(404,"Attachment not found")
        attachment_id=attachment.id
    row = TeamMessage(tenant_id=user.tenant_id, sender_id=user.id, sender_name=user.name, recipient_id=payload.recipient_id, room=room_key, message=payload.message.strip(), formatting=payload.formatting, attachment_id=attachment_id)
    db.add(row); db.commit(); db.refresh(row)
    return message_json(row)

@router.get("/export.csv")
def export_messages(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = actor(authorization, db); require_admin(user, db)
    rows = db.scalars(select(TeamMessage).where(TeamMessage.tenant_id == user.tenant_id).order_by(TeamMessage.created_at)).all()
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(["timestamp_utc","room","sender","sender_id","recipient_id","message","formatting","attachment_id"])
    for m in rows: writer.writerow([m.created_at.isoformat()+"Z",m.room,m.sender_name,m.sender_id,m.recipient_id or "",m.message,m.formatting,m.attachment_id or ""])
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=team-chat-export.csv"})
