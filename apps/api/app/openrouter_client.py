"""Small async OpenRouter chat-completions client.

This is a text-model adapter, not a realtime audio/WebRTC provider. Voice
runtime code must pair it with explicit speech-to-text and text-to-speech.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from .config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter is not configured or rejects a request."""


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # Avoid leaking request headers or API keys into logs/errors.
        try:
            detail = exc.read(1200).decode("utf-8", errors="replace")
        except Exception:
            detail = "provider returned an HTTP error"
        raise OpenRouterError(f"OpenRouter HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OpenRouterError(f"OpenRouter request failed: {type(exc).__name__}") from None
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise OpenRouterError("OpenRouter returned invalid JSON") from None
    if not isinstance(result, dict):
        raise OpenRouterError("OpenRouter returned an unexpected response")
    return result


class OpenRouterChatClient:
    """OpenRouter Chat Completions API wrapper with injectable transport for tests."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        timeout: float = 25.0,
        transport=None,
    ):
        self.api_key = (api_key if api_key is not None else settings.openrouter_api_key).strip()
        self.model = (model if model is not None else settings.openrouter_model).strip()
        self.timeout = timeout
        self._transport = transport or _post_json

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 500,
    ) -> str:
        if not self.api_key:
            raise OpenRouterError("OpenRouter is not configured (OPENROUTER_API_KEY is missing)")
        if not self.model:
            raise OpenRouterError("OpenRouter is not configured (OPENROUTER_MODEL is missing)")
        if not messages or any(
            not isinstance(m, dict)
            or m.get("role") not in {"system", "user", "assistant"}
            or not isinstance(m.get("content"), str)
            for m in messages
        ):
            raise ValueError("messages must contain role/content text entries")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": settings.public_app_url,
            "X-Title": settings.app_name,
        }
        try:
            response = await asyncio.to_thread(
                self._transport, OPENROUTER_URL, headers, payload, self.timeout
            )
        except OpenRouterError:
            raise
        except Exception as exc:
            raise OpenRouterError(f"OpenRouter transport failed: {type(exc).__name__}") from None
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            error = response.get("error") if isinstance(response, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            raise OpenRouterError(str(message or "OpenRouter response did not contain a completion")) from None
        if not isinstance(content, str) or not content.strip():
            raise OpenRouterError("OpenRouter returned an empty completion")
        return content.strip()
