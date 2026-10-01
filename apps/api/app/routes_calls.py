"""Call capture & QA routes.

Dashboard API for viewing captured calls, transcripts, audio playback,
and auto-detected flags.

Endpoints:
    GET  /api/v1/calls/recent          - recent calls (paginated)
    GET  /api/v1/calls/problems        - calls with flags
    GET  /api/v1/calls/{id}            - full call detail (turns + flags)
    GET  /api/v1/calls/{id}/audio/{side}/{turn}  - stream audio
    GET  /api/v1/calls/stats           - aggregate metrics
    GET  /api/v1/calls/flags/top       - most common flag types

All endpoints are tenant-scoped via the authenticated user's tenant.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select, func, desc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])


# ---------------------------------------------------------------------------
# Helper — resolve tenant from request
# ---------------------------------------------------------------------------

def _tenant_id_from_request(request: Request) -> Optional[str]:
    """Best-effort tenant resolution. Adjust to match your auth setup."""
    # If you have a dependency that sets request.state.tenant_id, use it.
    tid = getattr(request.state, "tenant_id", None)
    if tid:
        return tid
    # Fallback: read from query params (dev only)
    return request.query_params.get("tenant_id")


# ---------------------------------------------------------------------------
# Recent calls
# ---------------------------------------------------------------------------

@router.get("/recent")
async def recent_calls(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
):
    from .db import SessionLocal
    from .models_calls import CallRecording

    tenant_id = _tenant_id_from_request(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id required")

    db = SessionLocal()
    try:
        q = select(CallRecording).where(CallRecording.tenant_id == tenant_id)
        if status:
            q = q.where(CallRecording.status == status)
        rows = db.scalars(q.order_by(desc(CallRecording.started_at)).limit(limit)).all()

        return {
            "calls": [_recording_to_dict(r) for r in rows],
            "count": len(rows),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Problem calls (has flags)
# ---------------------------------------------------------------------------

@router.get("/problems")
async def problem_calls(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[str] = None,
):
    from .db import SessionLocal
    from .models_calls import CallRecording

    tenant_id = _tenant_id_from_request(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id required")

    db = SessionLocal()
    try:
        q = select(CallRecording).where(
            CallRecording.tenant_id == tenant_id,
            CallRecording.has_flags == True,
        )
        if severity:
            q = q.where(CallRecording.severity == severity)
        rows = db.scalars(q.order_by(desc(CallRecording.started_at)).limit(limit)).all()

        return {
            "calls": [_recording_to_dict(r) for r in rows],
            "count": len(rows),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Full call detail
# ---------------------------------------------------------------------------

@router.get("/{recording_id}")
async def call_detail(recording_id: str, request: Request):
    from .db import SessionLocal
    from .models_calls import CallRecording, CallTurn
    from .call_diagnostics import list_flags_for_recording

    tenant_id = _tenant_id_from_request(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id required")

    db = SessionLocal()
    try:
        rec = db.get(CallRecording, recording_id)
        if not rec or rec.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="call not found")

        turns = db.scalars(
            select(CallTurn)
            .where(CallTurn.recording_id == recording_id)
            .order_by(CallTurn.turn_number)
        ).all()

        flags = list_flags_for_recording(db, recording_id)

        return {
            "recording": _recording_to_dict(rec),
            "turns": [_turn_to_dict(t) for t in turns],
            "flags": flags,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Audio streaming
# ---------------------------------------------------------------------------

@router.get("/{recording_id}/audio/{side}/{turn_number}")
async def get_audio(recording_id: str, side: str, turn_number: int, request: Request):
    """Stream audio for a specific turn.

    side is 'customer' or 'ai'.
    """
    from .db import SessionLocal
    from .models_calls import CallRecording, CallTurn
    from .call_storage import load_audio

    tenant_id = _tenant_id_from_request(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id required")

    if side not in ("customer", "ai"):
        raise HTTPException(status_code=400, detail="side must be customer or ai")

    db = SessionLocal()
    try:
        rec = db.get(CallRecording, recording_id)
        if not rec or rec.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="call not found")

        turn = db.scalar(
            select(CallTurn).where(
                CallTurn.recording_id == recording_id,
                CallTurn.turn_number == turn_number,
            )
        )
        if not turn:
            raise HTTPException(status_code=404, detail="turn not found")

        url = turn.customer_audio_url if side == "customer" else turn.ai_audio_url
        if not url:
            raise HTTPException(status_code=404, detail="audio not recorded")

        data = load_audio(url)
        if not data:
            raise HTTPException(status_code=404, detail="audio missing from storage")

        return Response(content=data, media_type="audio/webm")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats/summary")
async def stats_summary(request: Request):
    from .db import SessionLocal
    from .models_calls import CallRecording

    tenant_id = _tenant_id_from_request(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id required")

    db = SessionLocal()
    try:
        total = db.scalar(
            select(func.count(CallRecording.id)).where(
                CallRecording.tenant_id == tenant_id
            )
        ) or 0
        with_flags = db.scalar(
            select(func.count(CallRecording.id)).where(
                CallRecording.tenant_id == tenant_id,
                CallRecording.has_flags == True,
            )
        ) or 0
        avg_duration = db.scalar(
            select(func.avg(CallRecording.duration_seconds)).where(
                CallRecording.tenant_id == tenant_id,
            )
        ) or 0
        avg_turns = db.scalar(
            select(func.avg(CallRecording.turn_count)).where(
                CallRecording.tenant_id == tenant_id,
            )
        ) or 0

        return {
            "total_calls": int(total),
            "calls_with_flags": int(with_flags),
            "clean_calls": int(total - with_flags),
            "error_rate_pct": round(100.0 * with_flags / max(1, total), 1),
            "avg_duration_seconds": int(avg_duration),
            "avg_turns_per_call": round(float(avg_turns), 1),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Top flag types
# ---------------------------------------------------------------------------

@router.get("/stats/flags")
async def top_flags(request: Request, limit: int = 10):
    from .db import SessionLocal
    from .models_calls import CallFlag, CallRecording

    tenant_id = _tenant_id_from_request(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="tenant_id required")

    db = SessionLocal()
    try:
        # Join flags with recordings to filter by tenant
        rows = db.execute(
            select(CallFlag.flag_type, func.count(CallFlag.id))
            .join(CallRecording, CallFlag.recording_id == CallRecording.id)
            .where(CallRecording.tenant_id == tenant_id)
            .group_by(CallFlag.flag_type)
            .order_by(func.count(CallFlag.id).desc())
            .limit(limit)
        ).all()

        return {
            "flags": [{"flag_type": r[0], "count": r[1]} for r in rows],
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _recording_to_dict(r) -> dict:
    return {
        "id": r.id,
        "customer_name": r.customer_name,
        "customer_phone": r.customer_phone,
        "channel": r.channel,
        "language_start": r.language_start,
        "language_end": r.language_end,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        "duration_seconds": r.duration_seconds,
        "turn_count": r.turn_count,
        "status": r.status,
        "outcome": r.outcome,
        "intent_final": r.intent_final,
        "has_flags": r.has_flags,
        "flag_count": r.flag_count,
        "severity": r.severity,
        "avg_turn_latency_ms": r.avg_turn_latency_ms,
        "total_customer_audio_bytes": r.total_customer_audio_bytes,
        "total_ai_audio_bytes": r.total_ai_audio_bytes,
    }


def _turn_to_dict(t) -> dict:
    return {
        "id": t.id,
        "turn_number": t.turn_number,
        "ts_started": t.ts_started.isoformat() if t.ts_started else None,
        "customer_text": t.customer_text,
        "customer_audio_url": t.customer_audio_url,
        "customer_audio_ms": t.customer_audio_ms,
        "stt_latency_ms": t.stt_latency_ms,
        "intent": t.intent,
        "confidence": t.confidence,
        "language": t.language,
        "entities": json.loads(t.entities_json or "{}"),
        "source": t.source,
        "handler_name": t.handler_name,
        "handler_succeeded": t.handler_succeeded,
        "state_before": t.state_before,
        "state_after": t.state_after,
        "cleared_at_set": t.cleared_at_set,
        "ai_text": t.ai_text,
        "ai_audio_url": t.ai_audio_url,
        "ai_audio_ms": t.ai_audio_ms,
        "tts_latency_ms": t.tts_latency_ms,
        "total_latency_ms": t.total_latency_ms,
        "tokens_used": t.tokens_used,
        "cost_usd": t.cost_usd,
        "error": t.error,
    }