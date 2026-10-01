# apps/api/app/booking_state.py
"""
Persistent per-conversation booking state.
Prevents the "AI forgets mid-booking" bug.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional

STALE_AFTER_MINUTES = 30


@dataclass
class BookingState:
    service: Optional[str] = None
    date: Optional[str] = None          # YYYY-MM-DD
    time: Optional[str] = None          # HH:MM (24h)
    awaiting: str = "idle"              # idle | date | time | confirm | confirm_and_book
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def reset(self):
        self.service = None
        self.date = None
        self.time = None
        self.awaiting = "idle"
        self.last_updated = datetime.utcnow().isoformat()

    def is_stale(self) -> bool:
        try:
            last = datetime.fromisoformat(self.last_updated)
            return datetime.utcnow() - last > timedelta(minutes=STALE_AFTER_MINUTES)
        except Exception:
            return True

    def to_dict(self):
        return asdict(self)


def load_state(store: dict, conversation_id: str) -> BookingState:
    """Load or create a booking state from your persistence layer."""
    raw = store.get(conversation_id)
    if not raw:
        state = BookingState()
    else:
        state = BookingState(**raw)
    if state.is_stale():
        state.reset()
    return state


def save_state(store: dict, conversation_id: str, state: BookingState):
    store[conversation_id] = state.to_dict()