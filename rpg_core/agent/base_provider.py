"""LLMProvider — abstract base class for LLM providers in RPG Agent.

All LLM providers (OpenAI, Anthropic, etc.) must implement this interface.
The current concrete implementation is ``OpenAIProvider``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from rpg_world.rpg_core.agent.agent_types import LLMResponse, ProviderChunk


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
    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        """Stream a chat completion, yielding ``ProviderChunk`` deltas.

        Args:
            messages: OpenAI-format message list.
            tools: Optional list of OpenAI tool/function schemas.

        Yields:
            ``ProviderChunk`` objects with incremental content / reasoning
            deltas.  The last yielded chunk carries ``tool_calls``,
            ``usage``, ``model``, ``finish_reason`` if available.
        """
        ...

    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model identifier for this provider."""
        ...
