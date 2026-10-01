"""Intent telemetry.

Records which path answered each message so operators can see the value of
the deterministic layers and the cost of the model fallback.

Storage is optional. If a database session is provided, records are written to
the message_telemetry table. Otherwise, an in-memory ring buffer keeps the most
recent N events (useful for tests and local development).

Design goals:
- never raise: telemetry failure must never break a reply
- no imports from models at module load: the model table may not exist yet
- cheap: one insert per message, no joins
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Record type
# ---------------------------------------------------------------------------

@dataclass
class TelemetryEvent:
    ts: float
    tenant_id: str
    conversation_id: str
    message: str
    intent: str
    confidence: float
    language: str
    source: str                # handler | knowledge | faq | llm | fallback | unconfigured_handoff
    handler: Optional[str] = None
    latency_ms: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# In-memory ring buffer (always available, used as a fallback and for tests)
# ---------------------------------------------------------------------------

_RING_SIZE = 1000
_RING: deque = deque(maxlen=_RING_SIZE)
_RING_LOCK = threading.Lock()


def _record_to_ring(event: TelemetryEvent) -> None:
    with _RING_LOCK:
        _RING.append(event)


def recent(limit: int = 50) -> list:
    """Return the most recent events (newest first)."""
    with _RING_LOCK:
        items = list(_RING)
    items.reverse()
    return [e.to_dict() for e in items[:limit]]


def clear() -> None:
    with _RING_LOCK:
        _RING.clear()


# ---------------------------------------------------------------------------
# Database persistence (lazy, defensive)
# ---------------------------------------------------------------------------

def _persist_to_db(db: Any, event: TelemetryEvent) -> None:
    """Best-effort insert into message_telemetry.

    Never raises. If the table does not exist yet, logs once at debug level
    and moves on, so the caller is unaffected.
    """
    try:
        from .models_analytics import MessageTelemetry
    except Exception:
        logger.debug("Telemetry model not available; skipping DB persist")
        return
    try:
        row = MessageTelemetry(
            tenant_id=event.tenant_id,
            conversation_id=event.conversation_id,
            message=event.message[:500],
            intent=event.intent,
            confidence=event.confidence,
            language=event.language,
            source=event.source,
            handler=event.handler,
            latency_ms=event.latency_ms,
            tokens_used=event.tokens_used,
            cost_usd=event.cost_usd,
        )
        db.add(row)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("Telemetry persist failed: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record(
    *,
    tenant_id: str,
    conversation_id: str,
    message: str,
    intent: str,
    confidence: float,
    language: str,
    source: str,
    handler: Optional[str] = None,
    latency_ms: int = 0,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    extra: Optional[dict] = None,
    db: Any = None,
) -> TelemetryEvent:
    """Record a single message event.

    Args:
        tenant_id: the tenant the message belongs to
        conversation_id: the conversation id
        message: the raw user message
        intent: the classified intent
        confidence: classifier confidence
        language: detected language
        source: the path that answered (handler | knowledge | faq | llm | fallback)
        handler: optional handler name if source == "handler"
        latency_ms: how long the answer took
        tokens_used: LLM tokens consumed (0 for non-LLM paths)
        cost_usd: cost in USD (0 for non-LLM paths)
        extra: any extra data worth keeping
        db: optional SQLAlchemy session. If provided, persists to the database.

    Returns:
        The TelemetryEvent that was recorded.
    """
    event = TelemetryEvent(
        ts=time.time(),
        tenant_id=tenant_id or "",
        conversation_id=conversation_id or "",
        message=message or "",
        intent=intent or "unknown",
        confidence=float(confidence or 0.0),
        language=language or "en",
        source=source or "unknown",
        handler=handler,
        latency_ms=int(latency_ms or 0),
        tokens_used=int(tokens_used or 0),
        cost_usd=float(cost_usd or 0.0),
        extra=extra or {},
    )
    _record_to_ring(event)
    if db is not None:
        _persist_to_db(db, event)
    return event


def summarize(events: list) -> dict:
    """Compute summary statistics from a list of event dicts.

    Useful for API endpoints and dashboards.
    """
    if not events:
        return {
            "total": 0,
            "by_source": {},
            "avg_latency_ms": 0,
            "total_tokens_used": 0,
            "estimated_cost_saved_usd": 0.0,
        }

    by_source: dict = {}
    total_latency = 0
    total_tokens = 0

    # Rough cost of one LLM message. Used only to estimate savings.
    # Update this if your model prices change.
    approx_cost_per_llm_call_usd = 0.0003

    for e in events:
        src = e.get("source") or "unknown"
        bucket = by_source.setdefault(src, {"count": 0, "latency_ms": 0, "tokens": 0})
        bucket["count"] += 1
        bucket["latency_ms"] += int(e.get("latency_ms") or 0)
        bucket["tokens"] += int(e.get("tokens_used") or 0)
        total_latency += int(e.get("latency_ms") or 0)
        total_tokens += int(e.get("tokens_used") or 0)

    # Average latency per source
    for src, bucket in by_source.items():
        bucket["avg_latency_ms"] = int(bucket["latency_ms"] / max(1, bucket["count"]))
        bucket["pct"] = round(100.0 * bucket["count"] / len(events), 1)

    non_llm_count = sum(
        b["count"] for s, b in by_source.items() if s != "llm" and s != "unknown"
    )
    estimated_saved = non_llm_count * approx_cost_per_llm_call_usd

    return {
        "total": len(events),
        "by_source": by_source,
        "avg_latency_ms": int(total_latency / len(events)),
        "total_tokens_used": total_tokens,
        "estimated_cost_saved_usd": round(estimated_saved, 4),
    }


def top_missed(events: list, limit: int = 10) -> list:
    """Return the most frequently asked messages that fell through to LLM/fallback.

    This is what tells you which new patterns would save the most tokens.
    """
    from collections import Counter
    missed = [
        (e.get("message") or "").strip().lower()
        for e in events
        if e.get("source") in ("llm", "fallback", "unknown")
    ]
    counter = Counter(m for m in missed if m)
    return [{"message": m, "count": c} for m, c in counter.most_common(limit)]