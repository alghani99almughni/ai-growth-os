from __future__ import annotations

from .openrouter_client import OpenRouterChatClient


class OpenRouterTurnService:
    """Text-turn adapter for a speech frontend that provides transcripts."""

    def __init__(self, client: OpenRouterChatClient | None = None):
        self.client = client or OpenRouterChatClient()

    async def respond(self, system_prompt: str, history: list[dict[str, str]], user_text: str) -> str:
        text = user_text.strip()
        if not text:
            raise ValueError("Customer transcript is empty")
        if len(text) > 4000:
            raise ValueError("Customer transcript is too long")
        messages = [{"role": "system", "content": system_prompt}]
        for item in history[-12:]:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content[:4000]})
        messages.append({"role": "user", "content": text})
        return await self.client.complete(messages, temperature=0.2, max_tokens=350)
