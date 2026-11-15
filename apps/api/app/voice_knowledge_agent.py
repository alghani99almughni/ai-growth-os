"""Deterministic, review-first learning agent for completed AI Voice calls.

The agent extracts customer/assistant turn pairs into pending knowledge candidates.
It never publishes knowledge automatically: Super Admin approval is required.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models_growth import CallRecord, KnowledgeCandidate
from .models_ai import InteractionEvent


def _transcript_lines(transcript: str) -> list[tuple[str, str]]:
    # Older voice sessions may have stored literal backslash-n separators.
    raw = transcript.replace("\\r\\n", "\\n").replace("\\n", "\n")
    turns: list[tuple[str, str]] = []
    for line in raw.splitlines():
        match = re.match(r"^\s*(CUSTOMER|AI|ASSISTANT)\s*:\s*(.*?)\s*$", line, re.I)
        if match and match.group(2):
            role = "CUSTOMER" if match.group(1).upper() == "CUSTOMER" else "AI"
            turns.append((role, match.group(2)))
    return turns


def process_call_transcript(db: Session, call: CallRecord, *, force: bool = False) -> dict:
    """Extract safe-to-review Q/A candidates once per call; no model/API is invoked."""
    existing_run = db.scalar(select(InteractionEvent).where(
        InteractionEvent.tenant_id == call.tenant_id,
        InteractionEvent.call_id == call.id,
        InteractionEvent.event_type == "voice_learning_processed",
    ).order_by(InteractionEvent.created_at.desc()).limit(1))
    if existing_run and not force:
        try:
            return {"processed": False, **json.loads(existing_run.payload_json or "{}")}
        except Exception:
            return {"processed": False, "created": 0, "reason": "already_processed"}

    turns = _transcript_lines(call.transcript or "")
    pairs: list[tuple[str, str]] = []
    pending_question: str | None = None
    for role, text in turns:
        if role == "CUSTOMER":
            pending_question = text
        elif role == "AI" and pending_question:
            # Exclude very short acknowledgements and operational status fragments.
            question = pending_question.strip()
            answer = text.strip()
            if len(question) >= 8 and len(answer) >= 12:
                pairs.append((question, answer))
            pending_question = None

    created = 0
    updated = 0
    for question, answer in pairs:
        normalized = " ".join(question.casefold().split())
        rows = db.scalars(select(KnowledgeCandidate).where(
            KnowledgeCandidate.tenant_id == call.tenant_id,
            KnowledgeCandidate.status.in_(["pending", "approved"]),
        ).order_by(KnowledgeCandidate.last_asked_at.desc()).limit(300)).all()
        candidate = next((row for row in rows if " ".join((row.question or "").casefold().split()) == normalized), None)
        if candidate:
            candidate.times_asked = (candidate.times_asked or 0) + 1
            candidate.last_asked_at = datetime.utcnow()
            # Do not overwrite a reviewed answer with a potentially incorrect AI answer.
            if candidate.status == "pending" and candidate.provider == "transcript_agent" and len(answer) > len(candidate.answer or ""):
                candidate.answer = answer
            updated += 1
        else:
            db.add(KnowledgeCandidate(
                tenant_id=call.tenant_id,
                question=question[:4000],
                answer=answer[:8000],
                language=call.language or "en",
                intent=call.intent,
                status="pending",
                source="voice_transcript",
                provider="transcript_agent",
                times_asked=1,
            ))
            created += 1

    payload = {"created": created, "updated": updated, "pairs_found": len(pairs)}
    if existing_run:
        existing_run.payload_json = json.dumps(payload)
        existing_run.created_at = datetime.utcnow()
    else:
        db.add(InteractionEvent(
            tenant_id=call.tenant_id,
            customer_id=call.customer_id,
            call_id=call.id,
            channel="voice",
            event_type="voice_learning_processed",
            payload_json=json.dumps(payload),
        ))
    db.commit()
    return {"processed": True, **payload}
