"""LLMProvider — abstract base class for LLM providers in RPG Agent.

All LLM providers (OpenAI, Anthropic, etc.) must implement this interface.
The current concrete implementation is ``OpenAIProvider``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from rpg_world.rpg_core.agent.types import LLMResponse


class LLMProvider(ABC):
    """Abstract LLM provider for RPG Agent."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Send messages to LLM and return a structured ``LLMResponse``.

        Args:
            messages: OpenAI-format message list.
            tools: Optional list of OpenAI tool/function schemas.

        Returns:
            ``LLMResponse`` with content, tool_calls, finish_reason,
            plus usage / model / reasoning metadata when available.
        """
        ...

    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model identifier for this provider."""
        ...
