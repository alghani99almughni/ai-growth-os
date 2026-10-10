from datetime import date
from types import SimpleNamespace

from app.brain import previous_booking_context
from app.models_ai import Conversation, ConversationMessage


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self):
        self.conversation = SimpleNamespace(state="booking_confirmation", cleared_at=None)
        self.user_messages = [
            SimpleNamespace(content="I want to book an appointment"),
            SimpleNamespace(content="possible for today"),
            SimpleNamespace(content="now"),
        ]
        self.assistant_message = SimpleNamespace(
            content=(
                "Now isn't available. The next available slot is "
                "Monday, October 12, 2026 at 9:00 AM. Shall I confirm that appointment?"
            )
        )

    def get(self, model, object_id):
        assert model is Conversation
        return self.conversation

    def scalars(self, query):
        return _Rows(self.user_messages)

    def scalar(self, query):
        return self.assistant_message


def test_confirmation_recovers_exact_next_available_slot_from_prompt():
    context = previous_booking_context(_FakeDB(), "conversation-1", "Yes, confirm it")

    assert context["resolved_date"] == date(2026, 10, 12)
    assert context["day"] == "monday"
    assert context["relative_day"] is None
    assert context["time"] == "9:00 AM"
