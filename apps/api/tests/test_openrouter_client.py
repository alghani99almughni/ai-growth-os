import asyncio

import pytest

from app.openrouter_client import OpenRouterChatClient, OpenRouterError, OPENROUTER_URL


def test_openrouter_posts_configured_model_and_returns_assistant_text():
    seen = {}

    def transport(url, headers, payload, timeout):
        seen.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {"choices": [{"message": {"content": "  Hello there.  "}}]}

    client = OpenRouterChatClient(
        api_key="test-key",
        model="qwen/qwen3-coder",
        timeout=7,
        transport=transport,
    )
    result = asyncio.run(client.complete([
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "Hello"},
    ]))

    assert result == "Hello there."
    assert seen["url"] == OPENROUTER_URL
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["payload"]["model"] == "qwen/qwen3-coder"
    assert seen["payload"]["messages"][1]["content"] == "Hello"
    assert seen["timeout"] == 7


def test_openrouter_missing_key_fails_without_transport_call():
    def transport(*args, **kwargs):
        raise AssertionError("transport must not be called")

    client = OpenRouterChatClient(api_key="", model="qwen/qwen3-coder", transport=transport)
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY"):
        asyncio.run(client.complete([{"role": "user", "content": "Hi"}]))


def test_openrouter_rejects_invalid_messages():
    client = OpenRouterChatClient(
        api_key="test-key",
        model="qwen/qwen3-coder",
        transport=lambda *args: {"choices": [{"message": {"content": "ok"}}]},
    )
    with pytest.raises(ValueError, match="role/content"):
        asyncio.run(client.complete([{"role": "developer", "content": "not supported"}]))


def test_openrouter_reports_missing_completion():
    client = OpenRouterChatClient(
        api_key="test-key",
        model="qwen/qwen3-coder",
        transport=lambda *args: {"choices": []},
    )
    with pytest.raises(OpenRouterError, match="did not contain a completion"):
        asyncio.run(client.complete([{"role": "user", "content": "Hi"}]))


def test_openrouter_rejects_empty_completion():
    client = OpenRouterChatClient(
        api_key="test-key",
        model="qwen/qwen3-coder",
        transport=lambda *args: {"choices": [{"message": {"content": "  "}}]},
    )
    with pytest.raises(OpenRouterError, match="empty completion"):
        asyncio.run(client.complete([{"role": "user", "content": "Hi"}]))
