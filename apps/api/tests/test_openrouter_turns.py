import asyncio

import pytest

from app.openrouter_turns import OpenRouterTurnService


class FakeClient:
    def __init__(self):
        self.messages = None

    async def complete(self, messages, **kwargs):
        self.messages = messages
        return "Hello, how can I help?"


def test_turn_service_builds_context_and_bounds_history():
    client = FakeClient()
    service = OpenRouterTurnService(client)
    history = []
    for i in range(15):
        history.append({"role": "user", "content": f"user-{i}"})
        history.append({"role": "assistant", "content": f"assistant-{i}"})
    result = asyncio.run(service.respond("Tenant policy", history, "  Hi  "))
    assert result == "Hello, how can I help?"
    assert client.messages[0] == {"role": "system", "content": "Tenant policy"}
    assert client.messages[-1] == {"role": "user", "content": "Hi"}
    assert len(client.messages) == 14
    assert client.messages[1]["content"] == "user-9"


def test_turn_service_rejects_empty_transcript():
    with pytest.raises(ValueError, match="empty"):
        asyncio.run(OpenRouterTurnService(FakeClient()).respond("system", [], "  "))


def test_turn_service_rejects_oversized_transcript():
    with pytest.raises(ValueError, match="too long"):
        asyncio.run(OpenRouterTurnService(FakeClient()).respond("system", [], "x" * 4001))
