from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import Tenant, Customer
from .models_growth import CallRecord
from .models_integrations import TenantIntegration
from .integrations import decrypt_channel_config
from .tenant_policy import tenant_policy, policy_context
from .brain import knowledge_context
from .agent_training import AGENT_TRAINING_CONTEXT
from .voice_gateway import VoiceGateway, VoiceProvider, GeminiLiveAdapter, OpenAIRealtimeAdapter
from .webcall_runtime import WebCallRuntime, wait_for_ice_timeout

router = APIRouter()
log = logging.getLogger("uvicorn.error")


def _verify_room_token(token: str, call_id: str) -> bool:
    try:
        parts = token.split(".")
        if len(parts) != 5 or parts[0] != "v2":
            return False
        _, token_call_id, audience, exp_text, signature = parts
        if token_call_id != call_id or audience != "call-customer":
            return False
        if int(exp_text) < int(time.time()):
            return False
        body = ".".join(parts[:4])
        expected = hmac.new(settings.jwt_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


def _system_prompt(tenant, customer, context: str, policy: dict[str, Any]) -> str:
    return f"""You are the AI customer engagement voice agent for {tenant.name}.

UNIVERSAL AGENT TRAINING:
{AGENT_TRAINING_CONTEXT}

TENANT POLICY:
{policy_context(policy)}

APPROVED BUSINESS CONTEXT:
{context}

BUSINESS PROFILE:
Address: {tenant.address or 'not configured'}
Phone: {tenant.phone or 'not configured'}
Website: {tenant.website or 'not configured'}

CUSTOMER:
Name: {customer.name if customer else 'Customer'}
Mobile: {customer.phone if customer else 'not provided'}

The customer identity has already been collected before this call. Do not ask for name or mobile again.
Resolve relative dates using the business timezone. Never invent business facts, prices, availability, policies, bookings or payment success.
If information is missing or unverified, say so briefly and offer a human follow-up instead of guessing.
If the caller interrupts, stop promptly and answer the newest complete request.
Reply in the caller's current language. Support English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi and Urdu, including natural code-switching.
Be concise, warm and conversational. Do not read database-style lists aloud.
"""


def _providers(db, tenant) -> list[VoiceProvider]:
    providers: list[VoiceProvider] = []
    key = settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key
    if key:
        rows = db.scalars(select(TenantIntegration).where(
            TenantIntegration.tenant_id == tenant.id,
            TenantIntegration.integration_key.in_(["gemini", "openai"]),
            TenantIntegration.status == "connected",
        )).all()
        for row in rows:
            try:
                cfg = decrypt_channel_config(row.config_encrypted, key)
                api_key = cfg.get("api_key") or cfg.get("access_token") or ""
                if not api_key:
                    continue
                if row.integration_key == "gemini":
                    model = cfg.get("realtime_model") or cfg.get("live_model") or settings.gemini_live_model
                    providers.append(VoiceProvider("gemini", model, api_key, priority=10))
                else:
                    model = cfg.get("realtime_model") or settings.openai_realtime_model
                    providers.append(VoiceProvider("openai", model, api_key, priority=20))
            except Exception:
                log.exception("WEB_CALL_TENANT_PROVIDER_CONFIG_FAILED tenant=%s", tenant.id)
    if settings.gemini_api_key:
        providers.append(VoiceProvider("gemini", settings.gemini_live_model, settings.gemini_api_key, priority=100))
    if settings.openai_api_key:
        providers.append(VoiceProvider("openai", settings.openai_realtime_model, settings.openai_api_key, priority=200))
    return providers


@router.websocket("/ws/public/webcall/{call_id}")
async def public_webcall(websocket: WebSocket, call_id: str, room_token: str | None = None):
    await websocket.accept()
    db = SessionLocal()
    runtime = None
    call_failed = False
    try:
        if not room_token or not _verify_room_token(room_token, call_id):
            await websocket.send_json({"type": "error", "code": "invalid_room_token"})
            await websocket.close(code=4403)
            return

        call = db.get(CallRecord, call_id)
        if not call or call.source != "pwa_voice":
            await websocket.send_json({"type": "error", "code": "call_not_found"})
            await websocket.close(code=4404)
            return
        age = (datetime.utcnow() - call.started_at).total_seconds() if call.started_at else 999999
        if call.status not in ("ringing", "connected") or age > 600:
            await websocket.send_json({"type": "error", "code": "call_not_active"})
            await websocket.close(code=4403)
            return

        tenant = db.get(Tenant, call.tenant_id)
        customer = db.get(Customer, call.customer_id) if call.customer_id else None
        if not tenant:
            await websocket.send_json({"type": "error", "code": "tenant_not_found"})
            await websocket.close(code=4404)
            return

        providers = _providers(db, tenant)
        if not providers:
            call_failed = True
            await websocket.send_json({"type": "error", "code": "ai_provider_unavailable", "recoverable": True})
            await websocket.close(code=1011)
            return

        runtime = WebCallRuntime(
            websocket,
            call_id,
            providers,
            _system_prompt(tenant, customer, knowledge_context(db, tenant.id), tenant_policy(db, tenant.id)),
        )
        runtime.gateway = VoiceGateway({"gemini": GeminiLiveAdapter(), "openai": OpenAIRealtimeAdapter()})

        await websocket.send_json({"type": "status", "status": "signaling_ready"})
        first = await websocket.receive_json()
        if first.get("type") != "offer":
            await websocket.send_json({"type": "error", "code": "offer_required"})
            return
        await runtime.setup_peer(first)

        provider, session = await runtime.gateway.connect_with_failover(
            providers,
            system_instruction=runtime.system_instruction,
            tools=[],
            state=runtime.state,
        )
        runtime.provider = provider
        runtime.session = session
        runtime.provider_task = asyncio.create_task(runtime.provider_loop())
        asyncio.create_task(wait_for_ice_timeout(runtime, 60.0))

        call.status = "connected"
        call.answered_at = datetime.utcnow()
        db.commit()
        await websocket.send_json({"type": "status", "status": "ai_connected", "provider": provider.name})

        greeting = f"Say this greeting naturally and then listen: Hello {customer.name if customer else 'there'}, welcome to {tenant.name}. How can I help you today?"
        await runtime.gateway.adapter_for(provider).send_text(session, greeting)

        while not runtime.closed:
            message = await websocket.receive_json()
            typ = message.get("type")
            if typ == "ice-candidate":
                try:
                    await runtime.add_remote_candidate(message.get("candidate") or message)
                except Exception as exc:
                    log.debug("WEB_CALL_ICE_ADD_FAILED call=%s error=%s", call_id, str(exc)[:160])
            elif typ == "interrupt":
                runtime.outgoing.clear()
                try:
                    await runtime.gateway.adapter_for(provider).interrupt(session)
                except Exception:
                    pass
            elif typ in {"hangup", "stop"}:
                break

    except Exception as exc:
        call_failed = True
        log.exception("WEB_CALL_RUNTIME_FAILED call=%s error=%s", call_id, str(exc)[:300])
        try:
            await websocket.send_json({"type": "error", "code": "webcall_runtime_failed", "message": str(exc)[:300], "recoverable": True})
        except Exception:
            pass
    finally:
        if runtime:
            await runtime.close()
        try:
            call = db.get(CallRecord, call_id)
            if call and call.status not in ("completed", "ended"):
                call.status = "failed" if call_failed else "completed"
                call.ended_at = datetime.utcnow()
                db.commit()
        except Exception:
            db.rollback()
        db.close()
