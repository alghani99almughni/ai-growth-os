"""Call diagnostics.

Analyzes a completed call and attaches CallFlag rows for any issues
detected. Uses cheap heuristics — no ML, no LLM.

Called automatically from CallRecorder.finish().
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

SLOW_TURN_MS = 5000
LOOP_REPEAT_COUNT = 3
STUCK_STATE_TURNS = 4
FALLBACK_CLUSTER = 3
LANGUAGE_FLIPS = 2
CANCEL_KEYWORDS = ("cancel", "no thanks", "stop", "forget it", "leave it",
                   "रद्द", "नहीं चाहिए", "कैंसिल")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_call(db: Session, recording_id: str) -> list:
    """Run all detectors against a recording. Returns list of flag dicts."""
    try:
        from .models_calls import CallRecording, CallTurn, CallFlag
    except Exception as exc:
        logger.debug("models_calls unavailable: %s", exc)
        return []

    try:
        recording = db.get(CallRecording, recording_id)
        if not recording:
            return []

        turns = db.scalars(
            select(CallTurn)
            .where(CallTurn.recording_id == recording_id)
            .order_by(CallTurn.turn_number)
        ).all()

        if not turns:
            return []

        flags = []
        flags.extend(_detect_loops(turns))
        flags.extend(_detect_stuck_state(turns))
        flags.extend(_detect_empty_replies(turns))
        flags.extend(_detect_fallback_cluster(turns))
        flags.extend(_detect_language_drift(turns))
        flags.extend(_detect_slow_turns(turns))
        flags.extend(_detect_ignored_cancellations(turns))
        flags.extend(_detect_dead_end(turns))

        # Write to DB
        highest_severity = "info"
        severity_rank = {"info": 1, "warning": 2, "error": 3}

        for f in flags:
            flag = CallFlag(
                recording_id=recording_id,
                turn_id=f.get("turn_id"),
                flag_type=f["flag_type"],
                severity=f.get("severity", "warning"),
                message=f.get("message", ""),
                details_json=json.dumps(f.get("details", {}), ensure_ascii=False),
            )
            db.add(flag)
            if severity_rank.get(flag.severity, 0) > severity_rank.get(highest_severity, 0):
                highest_severity = flag.severity

        if flags:
            recording.has_flags = True
            recording.flag_count = len(flags)
            recording.severity = highest_severity

        db.commit()
        return flags

    except Exception as exc:
        logger.exception("analyze_call failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return []


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_loops(turns) -> list:
    """Same AI text 3+ times in a row."""
    flags = []
    streak = 1
    prev_text = None
    for t in turns:
        text = (t.ai_text or "").strip().lower()
        if text and text == prev_text:
            streak += 1
        else:
            streak = 1
            prev_text = text
        if streak == LOOP_REPEAT_COUNT:
            flags.append({
                "flag_type": "loop_detected",
                "severity": "error",
                "turn_id": t.id,
                "message": f"AI repeated same reply {streak} times in a row",
                "details": {"repeated_text": (t.ai_text or "")[:200], "count": streak},
            })
    return flags


def _detect_stuck_state(turns) -> list:
    """State unchanged for 4+ turns."""
    flags = []
    streak = 1
    prev_state = None
    for t in turns:
        state = t.state_after
        if state and state == prev_state:
            streak += 1
        else:
            streak = 1
            prev_state = state
        if streak == STUCK_STATE_TURNS:
            flags.append({
                "flag_type": "stuck_state",
                "severity": "error",
                "turn_id": t.id,
                "message": f"Conversation state stuck on '{state}' for {streak} turns",
                "details": {"state": state, "turns": streak},
            })
    return flags


def _detect_empty_replies(turns) -> list:
    """AI returned nothing."""
    flags = []
    for t in turns:
        if not (t.ai_text or "").strip():
            flags.append({
                "flag_type": "empty_reply",
                "severity": "error",
                "turn_id": t.id,
                "message": f"AI returned an empty reply at turn {t.turn_number}",
                "details": {"turn": t.turn_number},
            })
    return flags


def _detect_fallback_cluster(turns) -> list:
    """3+ fallbacks in a single call."""
    fallback_sources = ("callback", "fallback", "unconfigured_handoff")
    fallback_turns = [t for t in turns if (t.source or "") in fallback_sources]
    if len(fallback_turns) >= FALLBACK_CLUSTER:
        return [{
            "flag_type": "fallback_cluster",
            "severity": "warning",
            "turn_id": fallback_turns[0].id,
            "message": f"{len(fallback_turns)} fallback replies in one call",
            "details": {"count": len(fallback_turns), "turns": [t.turn_number for t in fallback_turns]},
        }]
    return []


def _detect_language_drift(turns) -> list:
    """Language flipped 2+ times."""
    langs = [t.language for t in turns if t.language]
    if len(langs) < 3:
        return []
    flips = 0
    for a, b in zip(langs, langs[1:]):
        if a != b:
            flips += 1
    if flips >= LANGUAGE_FLIPS:
        return [{
            "flag_type": "language_drift",
            "severity": "warning",
            "turn_id": None,
            "message": f"Language flipped {flips} times during the call",
            "details": {"flips": flips, "languages": list(set(langs))},
        }]
    return []


def _detect_slow_turns(turns) -> list:
    """Any turn over 5 seconds."""
    flags = []
    for t in turns:
        if (t.total_latency_ms or 0) > SLOW_TURN_MS:
            flags.append({
                "flag_type": "slow_turn",
                "severity": "warning",
                "turn_id": t.id,
                "message": f"Turn {t.turn_number} took {t.total_latency_ms}ms",
                "details": {"turn": t.turn_number, "latency_ms": t.total_latency_ms},
            })
    return flags


def _detect_ignored_cancellations(turns) -> list:
    """Customer said 'cancel' 2+ times, but state stayed in booking."""
    cancel_turns = []
    for t in turns:
        text = (t.customer_text or "").lower()
        if any(k in text for k in CANCEL_KEYWORDS):
            cancel_turns.append(t)
    if len(cancel_turns) < 2:
        return []

    # Check if state remained in booking after the first cancel
    still_in_booking = any(
        (t.state_after or "").startswith("booking")
        for t in turns if t.turn_number >= cancel_turns[0].turn_number
    )
    if still_in_booking:
        return [{
            "flag_type": "cancellation_ignored",
            "severity": "error",
            "turn_id": cancel_turns[0].id,
            "message": f"Customer said 'cancel' {len(cancel_turns)} times but state remained in booking",
            "details": {"cancel_turns": [t.turn_number for t in cancel_turns]},
        }]
    return []


def _detect_dead_end(turns) -> list:
    """AI asked same question, customer answered, AI asked again."""
    flags = []
    for i in range(len(turns) - 2):
        a = (turns[i].ai_text or "").strip().lower()
        c = (turns[i + 1].customer_text or "").strip()
        b = (turns[i + 2].ai_text or "").strip().lower()
        if not a or not c or not b:
            continue
        # Very simple similarity: first 40 chars match
        if a[:40] and a[:40] == b[:40]:
            flags.append({
                "flag_type": "dead_end",
                "severity": "warning",
                "turn_id": turns[i + 2].id,
                "message": "AI asked the same question twice in a row",
                "details": {"ai_question": a[:120]},
            })
    return flags


# ---------------------------------------------------------------------------
# Query helpers (used by dashboard)
# ---------------------------------------------------------------------------

def list_flags_for_recording(db: Session, recording_id: str) -> list:
    """Return all flags on a recording."""
    try:
        from .models_calls import CallFlag
        rows = db.scalars(
            select(CallFlag)
            .where(CallFlag.recording_id == recording_id)
            .order_by(CallFlag.created_at)
        ).all()
        return [{
            "id": r.id,
            "flag_type": r.flag_type,
            "severity": r.severity,
            "message": r.message,
            "details": json.loads(r.details_json or "{}"),
            "turn_id": r.turn_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows]
    except Exception as exc:
        logger.debug("list_flags_for_recording failed: %s", exc)
        return []


def list_problem_calls(db: Session, tenant_id: str, limit: int = 50) -> list:
    """Return recent problem calls for the dashboard."""
    try:
        from .models_calls import CallRecording
        rows = db.scalars(
            select(CallRecording)
            .where(
                CallRecording.tenant_id == tenant_id,
                CallRecording.has_flags == True,
            )
            .order_by(CallRecording.started_at.desc())
            .limit(limit)
        ).all()
        return [{
            "id": r.id,
            "customer_name": r.customer_name,
            "customer_phone": r.customer_phone,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "duration_seconds": r.duration_seconds,
            "turn_count": r.turn_count,
            "flag_count": r.flag_count,
            "severity": r.severity,
            "outcome": r.outcome,
        } for r in rows]
    except Exception as exc:
        logger.debug("list_problem_calls failed: %s", exc)
        return []