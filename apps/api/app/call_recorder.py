"""Durable per-call recorder. Text is committed independently of audio."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CallRecorder:
    """One recorder per call; transcript text survives TTS/audio failures."""

    def __init__(
        self, db: Session, tenant_id: str, *, customer_id: Optional[str] = None,
        customer_name: str = "Guest", customer_phone: str = "", channel: str = "webrtc",
        language: str = "en", call_record_id: Optional[str] = None,
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
        self._turn_started_utc: Optional[datetime] = None
        self._total_customer_bytes = 0
        self._total_ai_bytes = 0
        self._latency_samples: list[int] = []

    def start(self) -> Optional[str]:
        """Persist call metadata before processing conversation turns."""
        try:
            from .models_calls import CallRecording
            rec = CallRecording(
                tenant_id=self.tenant_id, customer_id=self.customer_id,
                call_record_id=self.call_record_id, customer_name=self.customer_name,
                customer_phone=self.customer_phone, channel=self.channel,
                language_start=self.language_start, language_end=self.language_end,
                started_at=datetime.utcnow(), status="in_progress",
            )
            self.db.add(rec)
            self.db.commit()
            self.db.refresh(rec)
            self.recording_id = rec.id
            return rec.id
        except Exception:
            logger.exception("CallRecorder.start failed")
            self._rollback()
            return None

    def _rollback(self):
        try:
            self.db.rollback()
        except Exception:
            pass

    def begin_turn(self):
        self.turn_number += 1
        self._turn_started_at = time.monotonic()
        self._turn_started_utc = datetime.utcnow()
        self._current_turn_id = None

    def _save_audio(self, audio_bytes: Optional[bytes], side: str) -> Optional[str]:
        if not audio_bytes or not self.recording_id:
            return None
        try:
            from .call_storage import save_audio
            url = save_audio(audio_bytes, self.recording_id, f"t{self.turn_number}", side)
            if side == "customer":
                self._total_customer_bytes += len(audio_bytes)
            else:
                self._total_ai_bytes += len(audio_bytes)
            return url
        except Exception as exc:
            # Audio is optional; never roll back already persisted transcript text.
            logger.warning("%s audio save failed: %s", side, exc)
            return None

    def capture_customer(self, text: str, audio_bytes: Optional[bytes] = None, stt_latency_ms: int = 0):
        """Commit final customer STT immediately, before orchestration or TTS."""
        if not self.recording_id:
            return
        try:
            from .models_calls import CallTurn
            customer_url = self._save_audio(audio_bytes, "customer")
            turn = self.db.get(CallTurn, self._current_turn_id) if self._current_turn_id else None
            if turn is None:
                turn = CallTurn(
                    recording_id=self.recording_id,
                    turn_number=max(self.turn_number, 1),
                    ts_started=self._turn_started_utc or datetime.utcnow(),
                    customer_text=text or "",
                    customer_audio_url=customer_url,
                    stt_latency_ms=stt_latency_ms,
                    language=self.language_start,
                )
                self.db.add(turn)
            else:
                turn.customer_text = text or ""
                turn.customer_audio_url = customer_url
                turn.stt_latency_ms = stt_latency_ms
            self.db.commit()
            self.db.refresh(turn)
            self._current_turn_id = turn.id
        except Exception:
            logger.exception("customer transcript persistence failed")
            self._rollback()

    def capture_ai(self, text: str, audio_bytes: Optional[bytes] = None, tts_latency_ms: int = 0):
        """Commit assistant text independently; create a turn if no STT turn exists."""
        if not self.recording_id:
            return
        try:
            from .models_calls import CallTurn
            ai_url = self._save_audio(audio_bytes, "ai")
            now = datetime.utcnow()
            elapsed_ms = int((time.monotonic() - self._turn_started_at) * 1000) if self._turn_started_at else 0
            turn = self.db.get(CallTurn, self._current_turn_id) if self._current_turn_id else None
            if turn is None:
                turn = CallTurn(
                    recording_id=self.recording_id,
                    turn_number=max(self.turn_number, 1),
                    ts_started=self._turn_started_utc or now,
                    customer_text="",
                    language=self.language_end,
                )
                self.db.add(turn)
            turn.ai_text = text or ""
            turn.ai_audio_url = ai_url
            turn.tts_latency_ms = tts_latency_ms
            turn.total_latency_ms = elapsed_ms
            turn.ts_ended = now
            self.db.commit()
            self.db.refresh(turn)
            self._current_turn_id = turn.id
            self._latency_samples.append(elapsed_ms)
        except Exception:
            logger.exception("assistant transcript persistence failed")
            self._rollback()

    def record_transcription_gap(self, reason: str):
        """Persist an explicit STT failure marker; never invent missing speech."""
        if not self.recording_id:
            return
        try:
            from .models_calls import CallTurn
            self.turn_number += 1
            now = datetime.utcnow()
            turn = CallTurn(
                recording_id=self.recording_id, turn_number=self.turn_number,
                ts_started=now, ts_ended=now, customer_text="", ai_text="",
                language=self.language_end, source="stt_gap",
                error=("transcription_gap: " + (reason or "unknown"))[:4000],
            )
            self.db.add(turn)
            self.db.commit()
        except Exception:
            logger.exception("transcription gap persistence failed")
            self._rollback()

    def annotate_turn(self, **fields):
        if not self._current_turn_id:
            return
        try:
            from .models_calls import CallTurn
            turn = self.db.get(CallTurn, self._current_turn_id)
            if not turn:
                return
            for key, value in fields.items():
                if hasattr(turn, key):
                    setattr(turn, key, value)
            self.db.commit()
        except Exception:
            logger.exception("turn annotation failed")
            self._rollback()

    def finish(self, outcome: Optional[str] = None, status: str = "completed"):
        """Close call metadata even when optional audio/diagnostics failed."""
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
                rec.duration_seconds = max(0, int((ended - rec.started_at).total_seconds()))
            rec.turn_count = self.turn_number
            rec.status = status
            rec.outcome = outcome
            rec.language_end = self.language_end
            rec.total_customer_audio_bytes = self._total_customer_bytes
            rec.total_ai_audio_bytes = self._total_ai_bytes
            if self._latency_samples:
                rec.avg_turn_latency_ms = int(sum(self._latency_samples) / len(self._latency_samples))
            self.db.commit()
        except Exception:
            logger.exception("CallRecorder.finish failed")
            self._rollback()
            return
        try:
            from .call_diagnostics import analyze_call
            analyze_call(self.db, self.recording_id)
        except Exception as exc:
            logger.warning("call diagnostics failed: %s", exc)


def record_offline_call(
    db: Session, tenant_id: str, *, customer_name: str, customer_phone: str,
    language: str, turn_pairs: list, outcome: Optional[str] = None,
) -> Optional[str]:
    """Persist a recovered call from ordered customer/assistant text pairs."""
    recorder = CallRecorder(
        db, tenant_id, customer_name=customer_name, customer_phone=customer_phone,
        channel="offline_recovered", language=language,
    )
    recording_id = recorder.start()
    if not recording_id:
        return None
    for pair in turn_pairs or []:
        recorder.begin_turn()
        recorder.capture_customer(pair.get("customer_text", ""), pair.get("customer_audio"))
        recorder.capture_ai(pair.get("ai_text", ""), pair.get("ai_audio"))
        if pair.get("intent"):
            recorder.annotate_turn(intent=pair["intent"])
    recorder.finish(outcome=outcome or "offline_recovered")
    return recording_id
