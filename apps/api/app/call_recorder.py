"""Call recorder.

Server-side recorder for call capture. One instance per call. Every
exchange (customer message + AI reply) is written as a CallTurn with
audio URLs and metadata.

Never raises. Recording failures must not break the call itself.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------

class CallRecorder:
    """Server-side recorder for one call."""

    def __init__(
        self,
        db: Session,
        tenant_id: str,
        *,
        customer_id: Optional[str] = None,
        customer_name: str = "Guest",
        customer_phone: str = "",
        channel: str = "webrtc",
        language: str = "en",
        call_record_id: Optional[str] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self.channel = channel
        self.language_start = language
        self.language_end = language
        self.call_record_id = call_record_id

        self.recording_id: Optional[str] = None
        self.turn_number = 0
        self._current_turn_id: Optional[str] = None
        self._turn_started_at: Optional[float] = None
        self._total_customer_bytes = 0
        self._total_ai_bytes = 0
        self._latency_samples = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> Optional[str]:
        """Create the CallRecording row. Returns recording_id or None."""
        try:
            from .models_calls import CallRecording
            rec = CallRecording(
                tenant_id=self.tenant_id,
                customer_id=self.customer_id,
                call_record_id=self.call_record_id,
                customer_name=self.customer_name,
                customer_phone=self.customer_phone,
                channel=self.channel,
                language_start=self.language_start,
                language_end=self.language_end,
                started_at=datetime.utcnow(),
                status="in_progress",
            )
            self.db.add(rec)
            self.db.commit()
            self.db.refresh(rec)
            self.recording_id = rec.id
            return rec.id
        except Exception as exc:
            logger.exception("CallRecorder.start failed: %s", exc)
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def begin_turn(self):
        """Mark the start of a new turn."""
        self.turn_number += 1
        self._turn_started_at = time.time()
        self._current_turn_id = None

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture_customer(
        self,
        text: str,
        audio_bytes: Optional[bytes] = None,
        stt_latency_ms: int = 0,
    ):
        """Save the customer's audio + text for the current turn."""
        if not self.recording_id:
            return
        self._pending_customer = {
            "text": text or "",
            "audio_bytes": audio_bytes,
            "stt_latency_ms": stt_latency_ms,
        }

    def capture_ai(
        self,
        text: str,
        audio_bytes: Optional[bytes] = None,
        tts_latency_ms: int = 0,
    ):
        """Save the AI's audio + text, then commit the whole turn."""
        if not self.recording_id:
            return
        cust = getattr(self, "_pending_customer", {}) or {}
        turn_started = self._turn_started_at or time.time()
        latency_ms = int((time.time() - turn_started) * 1000)
        self._latency_samples.append(latency_ms)

        # Save audio
        customer_url = None
        ai_url = None
        cust_bytes = cust.get("audio_bytes")
        if cust_bytes:
            try:
                from .call_storage import save_audio
                customer_url = save_audio(
                    cust_bytes, self.recording_id, f"t{self.turn_number}", "customer"
                )
                self._total_customer_bytes += len(cust_bytes)
            except Exception as exc:
                logger.debug("customer audio save failed: %s", exc)

        if audio_bytes:
            try:
                from .call_storage import save_audio
                ai_url = save_audio(
                    audio_bytes, self.recording_id, f"t{self.turn_number}", "ai"
                )
                self._total_ai_bytes += len(audio_bytes)
            except Exception as exc:
                logger.debug("ai audio save failed: %s", exc)

        # Save the turn row
        try:
            from .models_calls import CallTurn
            turn = CallTurn(
                recording_id=self.recording_id,
                turn_number=self.turn_number,
                ts_started=datetime.fromtimestamp(turn_started),
                ts_ended=datetime.utcnow(),
                customer_text=cust.get("text", ""),
                customer_audio_url=customer_url,
                customer_audio_ms=0,
                stt_latency_ms=cust.get("stt_latency_ms", 0),
                ai_text=text or "",
                ai_audio_url=ai_url,
                ai_audio_ms=0,
                tts_latency_ms=tts_latency_ms,
                total_latency_ms=latency_ms,
            )
            self.db.add(turn)
            self.db.commit()
            self.db.refresh(turn)
            self._current_turn_id = turn.id
        except Exception as exc:
            logger.exception("turn save failed: %s", exc)
            try:
                self.db.rollback()
            except Exception:
                pass

        self._pending_customer = {}

    # ------------------------------------------------------------------
    # Metadata annotation
    # ------------------------------------------------------------------

    def annotate_turn(self, **fields):
        """Update the current turn with extra metadata.

        Accepts: intent, confidence, language, entities_json, source,
        handler_name, handler_succeeded, state_before, state_after,
        cleared_at_set, tokens_used, cost_usd, error.
        """
        if not self._current_turn_id:
            return
        try:
            from .models_calls import CallTurn
            turn = self.db.get(CallTurn, self._current_turn_id)
            if not turn:
                return
            for k, v in fields.items():
                if hasattr(turn, k):
                    setattr(turn, k, v)
            self.db.commit()
        except Exception as exc:
            logger.debug("annotate_turn failed: %s", exc)
            try:
                self.db.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Finish
    # ------------------------------------------------------------------

    def finish(self, outcome: Optional[str] = None, status: str = "completed"):
        """Close the recording, run diagnostics, save flags."""
        if not self.recording_id:
            return
        try:
            from .models_calls import CallRecording
            rec = self.db.get(CallRecording, self.recording_id)
            if not rec:
                return

            ended = datetime.utcnow()
            rec.ended_at = ended
            if rec.started_at:
                rec.duration_seconds = int((ended - rec.started_at).total_seconds())
            rec.turn_count = self.turn_number
            rec.status = status
            rec.outcome = outcome
            rec.language_end = self.language_end
            rec.total_customer_audio_bytes = self._total_customer_bytes
            rec.total_ai_audio_bytes = self._total_ai_bytes
            if self._latency_samples:
                rec.avg_turn_latency_ms = int(
                    sum(self._latency_samples) / len(self._latency_samples)
                )
            self.db.commit()

            # Run diagnostics
            try:
                from .call_diagnostics import analyze_call
                analyze_call(self.db, self.recording_id)
            except Exception as exc:
                logger.debug("diagnostics failed: %s", exc)
        except Exception as exc:
            logger.exception("CallRecorder.finish failed: %s", exc)
            try:
                self.db.rollback()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Convenience: record a full offline call in one call
# ---------------------------------------------------------------------------

def record_offline_call(
    db: Session,
    tenant_id: str,
    *,
    customer_name: str,
    customer_phone: str,
    language: str,
    turn_pairs: list,
    outcome: Optional[str] = None,
) -> Optional[str]:
    """Record a list of turns from a recovered offline call.

    turn_pairs is a list of dicts:
        [{"customer_text": "...", "ai_text": "..."}, ...]

    Audio bytes are optional per turn; if present, they will be stored.
    Returns the recording_id.
    """
    rec = CallRecorder(
        db, tenant_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        channel="offline_recovered",
        language=language,
    )
    rid = rec.start()
    if not rid:
        return None

    for pair in turn_pairs or []:
        rec.begin_turn()
        rec.capture_customer(
            text=pair.get("customer_text", ""),
            audio_bytes=pair.get("customer_audio"),
        )
        rec.capture_ai(
            text=pair.get("ai_text", ""),
            audio_bytes=pair.get("ai_audio"),
        )
        if pair.get("intent"):
            rec.annotate_turn(intent=pair["intent"])

    rec.finish(outcome=outcome or "offline_recovered")
    return rid