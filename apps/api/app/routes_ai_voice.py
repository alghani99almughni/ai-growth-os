"""Tenant and platform control-plane APIs for AI Voice.

The router factory receives the existing application auth dependencies so this
feature shares AI Growth OS identity, tenant scoping and Super Admin RBAC.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models_ai_voice import DidNumber, SipTrunk, VoiceAgentConfig
from .integrations import encrypt_channel_config


E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    industry_template: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=2000)
    language_codes: list[str] = Field(default_factory=lambda: ["en", "hi", "te"], max_length=20)
    greeting: str = Field(default="", max_length=2000)
    operating_instructions: str = Field(default="", max_length=12000)
    human_handoff_enabled: bool = True
    recording_enabled: bool = True


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    industry_template: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    language_codes: list[str] | None = Field(default=None, max_length=20)
    greeting: str | None = Field(default=None, max_length=2000)
    operating_instructions: str | None = Field(default=None, max_length=12000)
    human_handoff_enabled: bool | None = None
    recording_enabled: bool | None = None
    status: str | None = Field(default=None, pattern="^(draft|published|paused|archived)$")


class TrunkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    registrar_host: str = Field(min_length=1, max_length=255)
    registrar_port: int = Field(default=5060, ge=1, le=65535)
    transport: str = Field(default="udp", pattern="^(udp|tcp|tls|wss)$")
    auth_username: str | None = Field(default=None, max_length=160)
    auth_password: str | None = Field(default=None, max_length=512)
    outbound_proxy: str | None = Field(default=None, max_length=255)
    direction: str = Field(default="bidirectional", pattern="^(inbound|outbound|bidirectional)$")


class DidCreate(BaseModel):
    e164_number: str
    trunk_id: str
    provider_number_id: str | None = Field(default=None, max_length=160)

    @classmethod
    def validate_number(cls, value):
        if not E164.fullmatch(value or ""):
            raise ValueError("DID must be in E.164 format, e.g. +919876543210")
        return value


class DidAssign(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=36)
    agent_id: str | None = Field(default=None, max_length=36)


class DidRoute(BaseModel):
    agent_id: str | None = Field(default=None, max_length=36)


def _trunk_dict(row: SipTrunk) -> dict:
    return {
        "id": row.id, "tenant_id": row.tenant_id, "name": row.name,
        "provider": row.provider, "registrar_host": row.registrar_host,
        "registrar_port": row.registrar_port, "transport": row.transport,
        "auth_username": row.auth_username, "outbound_proxy": row.outbound_proxy,
        "direction": row.direction, "status": row.status,
        "last_health_at": row.last_health_at.isoformat() if row.last_health_at else None,
        "last_health_error": row.last_health_error,
    }


def _agent_dict(row: VoiceAgentConfig) -> dict:
    import json
    return {
        "id": row.id, "tenant_id": row.tenant_id, "name": row.name,
        "industry_template": row.industry_template, "description": row.description,
        "language_codes": json.loads(row.language_codes_json or "[]"),
        "voice_provider": row.voice_provider, "voice_profile": row.voice_profile,
        "greeting": row.greeting, "operating_instructions": row.operating_instructions,
        "knowledge_scope": row.knowledge_scope, "human_handoff_enabled": row.human_handoff_enabled,
        "recording_enabled": row.recording_enabled, "status": row.status,
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


def _did_dict(row: DidNumber) -> dict:
    return {
        "id": row.id, "tenant_id": row.tenant_id, "trunk_id": row.trunk_id,
        "agent_id": row.agent_id, "e164_number": row.e164_number,
        "provider_number_id": row.provider_number_id, "inbound_enabled": row.inbound_enabled,
        "outbound_caller_id_enabled": row.outbound_caller_id_enabled,
        "status": row.status, "provision_state": row.provision_state,
    }


def build_ai_voice_router(get_current_user: Callable, get_db: Callable,
                          require_tenant: Callable, require_platform_admin: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/v1/ai-voice", tags=["AI Voice"])

    def store_trunk(db: Session, tenant_id: str | None, payload: TrunkCreate):
        if not settings.integration_credential_encryption_key:
            raise HTTPException(503, "SIP credential encryption is not configured")
        encrypted = None
        if payload.auth_password:
            try:
                encrypted = encrypt_channel_config({"password": payload.auth_password}, settings.integration_credential_encryption_key)
            except Exception:
                raise HTTPException(503, "Unable to encrypt SIP credentials")
        row = SipTrunk(
            id=str(uuid.uuid4()), tenant_id=tenant_id, name=payload.name.strip(),
            provider=payload.provider.strip(), registrar_host=payload.registrar_host.strip(),
            registrar_port=payload.registrar_port, transport=payload.transport,
            auth_username=payload.auth_username, credentials_ciphertext=encrypted,
            outbound_proxy=payload.outbound_proxy, direction=payload.direction, status="pending",
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except Exception:
            db.rollback()
            raise HTTPException(409, "A trunk with this name already exists for this tenant")
        return row

    @router.get("/agents")
    def list_agents(user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_tenant(user, user.tenant_id)
        rows = db.scalars(select(VoiceAgentConfig).where(
            VoiceAgentConfig.tenant_id == user.tenant_id,
            VoiceAgentConfig.status != "archived"
        ).order_by(VoiceAgentConfig.created_at.desc())).all()
        return {"items": [_agent_dict(row) for row in rows]}

    @router.post("/agents", status_code=201)
    def create_agent(payload: AgentCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_tenant(user, user.tenant_id)
        row = VoiceAgentConfig(
            id=str(uuid.uuid4()), tenant_id=user.tenant_id, name=payload.name.strip(),
            industry_template=payload.industry_template, description=payload.description,
            language_codes_json=__import__("json").dumps(payload.language_codes),
            greeting=payload.greeting, operating_instructions=payload.operating_instructions,
            human_handoff_enabled=payload.human_handoff_enabled,
            recording_enabled=payload.recording_enabled, status="draft",
        )
        db.add(row); db.commit(); db.refresh(row)
        return _agent_dict(row)

    @router.patch("/agents/{agent_id}")
    def update_agent(agent_id: str, payload: AgentUpdate, user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_tenant(user, user.tenant_id)
        import json
        row = db.scalar(select(VoiceAgentConfig).where(
            VoiceAgentConfig.id == agent_id, VoiceAgentConfig.tenant_id == user.tenant_id
        ))
        if not row:
            raise HTTPException(404, "Agent not found")
        values = payload.model_dump(exclude_unset=True)
        if "language_codes" in values:
            row.language_codes_json = json.dumps(values.pop("language_codes"))
        for key, value in values.items():
            setattr(row, key, value)
        if row.status == "published" and not row.published_at:
            row.published_at = datetime.utcnow()
        db.commit(); db.refresh(row)
        return _agent_dict(row)

    @router.get("/sip-trunks")
    def list_tenant_trunks(user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_tenant(user, user.tenant_id)
        rows = db.scalars(select(SipTrunk).where(SipTrunk.tenant_id == user.tenant_id)).all()
        return {"items": [_trunk_dict(row) for row in rows]}

    @router.post("/sip-trunks", status_code=201)
    def create_tenant_trunk(payload: TrunkCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_tenant(user, user.tenant_id)
        return _trunk_dict(store_trunk(db, user.tenant_id, payload))

    @router.get("/dids")
    def list_tenant_dids(user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_tenant(user, user.tenant_id)
        rows = db.scalars(select(DidNumber).where(DidNumber.tenant_id == user.tenant_id)).all()
        return {"items": [_did_dict(row) for row in rows]}

    @router.post("/dids/{did_id}/route")
    def route_tenant_did(did_id: str, payload: DidRoute, user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_tenant(user, user.tenant_id)
        row = db.scalar(select(DidNumber).where(DidNumber.id == did_id, DidNumber.tenant_id == user.tenant_id))
        if not row:
            raise HTTPException(404, "DID not found")
        agent_id = payload.agent_id
        if agent_id:
            agent = db.scalar(select(VoiceAgentConfig).where(
                VoiceAgentConfig.id == agent_id, VoiceAgentConfig.tenant_id == user.tenant_id,
                VoiceAgentConfig.status == "published"
            ))
            if not agent:
                raise HTTPException(400, "Select a published agent belonging to this tenant")
        row.agent_id = agent_id
        db.commit()
        return _did_dict(row)

    @router.get("/platform/sip-trunks")
    def platform_list_trunks(user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_platform_admin(user)
        rows = db.scalars(select(SipTrunk).order_by(SipTrunk.created_at.desc())).all()
        return {"items": [_trunk_dict(row) for row in rows]}

    @router.post("/platform/sip-trunks", status_code=201)
    def platform_create_trunk(payload: TrunkCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_platform_admin(user)
        return _trunk_dict(store_trunk(db, None, payload))

    @router.get("/platform/dids")
    def platform_list_dids(user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_platform_admin(user)
        rows = db.scalars(select(DidNumber).order_by(DidNumber.created_at.desc())).all()
        return {"items": [_did_dict(row) for row in rows]}

    @router.post("/platform/dids", status_code=201)
    def platform_create_did(payload: DidCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_platform_admin(user)
        number = payload.e164_number.strip()
        if not E164.fullmatch(number):
            raise HTTPException(422, "DID must be in E.164 format")
        trunk = db.get(SipTrunk, payload.trunk_id)
        if not trunk:
            raise HTTPException(404, "SIP trunk not found")
        row = DidNumber(id=str(uuid.uuid4()), trunk_id=trunk.id, e164_number=number,
                        provider_number_id=payload.provider_number_id, tenant_id=None, status="inventory")
        db.add(row)
        try:
            db.commit(); db.refresh(row)
        except Exception:
            db.rollback()
            raise HTTPException(409, "DID already exists")
        return _did_dict(row)

    @router.post("/platform/dids/{did_id}/assign")
    def platform_assign_did(did_id: str, payload: DidAssign, user=Depends(get_current_user), db: Session = Depends(get_db)):
        require_platform_admin(user)
        row = db.get(DidNumber, did_id)
        if not row:
            raise HTTPException(404, "DID not found")
        if row.tenant_id and row.tenant_id != payload.tenant_id:
            raise HTTPException(409, "DID is already assigned; unassign it before reassignment")
        if payload.agent_id:
            agent = db.scalar(select(VoiceAgentConfig).where(
                VoiceAgentConfig.id == payload.agent_id, VoiceAgentConfig.tenant_id == payload.tenant_id,
                VoiceAgentConfig.status == "published"
            ))
            if not agent:
                raise HTTPException(400, "Agent must be published and belong to the target tenant")
        row.tenant_id = payload.tenant_id
        row.agent_id = payload.agent_id
        row.status = "assigned"
        db.commit()
        return _did_dict(row)

    return router
