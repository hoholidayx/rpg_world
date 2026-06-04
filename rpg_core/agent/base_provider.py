"""LLMProvider — abstract base class for LLM providers in RPG Agent.

All LLM providers (OpenAI, Anthropic, etc.) must implement this interface.
The current concrete implementation is ``OpenAIProvider``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract LLM provider for RPG Agent."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Send messages to LLM and return a result dict.

        Args:
            messages: OpenAI-format message list.
            tools: Optional list of OpenAI tool/function schemas.

        Returns:
            A dict with keys:
                ``content`` — text content (may be empty when tool_calls present)
                ``tool_calls`` — list of OpenAI tool-call dicts, or ``None``
                ``finish_reason`` — ``"stop"``, ``"tool_calls"``, etc.
        """
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model identifier for this provider."""
        pass
