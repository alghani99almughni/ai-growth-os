"""Internal voice gateway.

The business voice/session layer talks only to this interface. Provider-specific
realtime transports stay behind adapters so the product is not architecturally
locked to a single vendor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class VoiceProvider:
    name: str
    model: str
    api_key: str
    priority: int = 100
    enabled: bool = True


class VoiceProviderAdapter(Protocol):
    name: str

    async def connect(
        self,
        provider: VoiceProvider,
        *,
        system_instruction: str,
        tools: list[dict[str, Any]],
    ) -> Any:
        """Return a provider session/transport."""


class VoiceGateway:
    """Provider-neutral orchestration boundary for realtime voice.

    The gateway owns provider selection and failover policy. Concrete realtime
    implementations are injected as adapters. This first version intentionally
    keeps the existing Gemini Live transport behind an adapter rather than
    duplicating a realtime media server.
    """

    def __init__(self, adapters: dict[str, VoiceProviderAdapter]):
        self.adapters = adapters

    def ordered(self, providers: list[VoiceProvider]) -> list[VoiceProvider]:
        return sorted(
            (p for p in providers if p.enabled and p.name in self.adapters),
            key=lambda p: (p.priority, p.name),
        )

    def adapter_for(self, provider: VoiceProvider) -> VoiceProviderAdapter:
        return self.adapters[provider.name]
