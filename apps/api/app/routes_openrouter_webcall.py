from __future__ import annotations

from datetime import datetime
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .db import SessionLocal
from .models import Customer, Tenant
from .models_growth import CallRecord
from .brain import knowledge_context
from .tenant_policy import tenant_policy
from .routes_webcall import _system_prompt, _verify_room_token
from .openrouter_client import OpenRouterError
from .openrouter_turns import OpenRouterTurnService

router = APIRouter()
log = logging.getLogger("uvicorn.error")


class OpenRouterTurnPayload(BaseModel):
    room_token: str = Field(min_length=1, max_length=512)
    text: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)


@router.post("/api/v1/public/webcall/{call_id}/turn")
async def openrouter_webcall_turn(call_id: str, payload: OpenRouterTurnPayload):
    if not _verify_room_token(payload.room_token, call_id):
        raise HTTPException(status_code=403, detail="Invalid or expired call token")

    db = SessionLocal()
    try:
        call = db.get(CallRecord, call_id)
        if not call or call.source != "pwa_voice":
            raise HTTPException(status_code=404, detail="Call not found")
        age = (datetime.utcnow() - call.started_at).total_seconds() if call.started_at else 999999
        if call.status not in ("ringing", "connected") or age > 600:
            raise HTTPException(status_code=409, detail="Call is no longer active")

        tenant = db.get(Tenant, call.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Business not found")
        customer = db.get(Customer, call.customer_id) if call.customer_id else None
        system_prompt = _system_prompt(
            tenant,
            customer,
            knowledge_context(db, tenant.id),
            tenant_policy(db, tenant.id),
        )
    finally:
        db.close()

    try:
        reply = await OpenRouterTurnService().respond(system_prompt, payload.history, payload.text.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except OpenRouterError:
        log.exception("OPENROUTER_WEB_CALL_TURN_FAILED call=%s", call_id)
        raise HTTPException(status_code=502, detail="OpenRouter could not generate a reply. Check server configuration and provider status.") from None

    return {"text": reply, "provider": "openrouter"}


@router.post("/api/v1/public/webcall/{call_id}/end")
async def end_openrouter_webcall(call_id: str, payload: OpenRouterTurnPayload):
    if not _verify_room_token(payload.room_token, call_id):
        raise HTTPException(status_code=403, detail="Invalid or expired call token")
    db = SessionLocal()
    try:
        call = db.get(CallRecord, call_id)
        if not call or call.source != "pwa_voice":
            raise HTTPException(status_code=404, detail="Call not found")
        if call.status not in ("completed", "ended", "failed"):
            call.status = "completed"
            call.ended_at = datetime.utcnow()
            db.commit()
        return {"status": call.status}
    finally:
        db.close()
