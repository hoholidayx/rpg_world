"""Abstract LLM provider interface used across the project.

The unified ``LLMProvider`` covers both chat-style completion and text
embedding so business code never needs to know which concrete provider
is in use for a given ``biz_key``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from rpg_core.llm.types import LLMResponse, ProviderChunk


class EmbeddingProviderError(Exception):
    """Raised when the embedding provider cannot fulfil a request."""


class LLMProvider(ABC):
    """Unified LLM provider — chat completion + optional embedding.

    Chat methods are always required; embedding methods raise
    ``NotImplementedError`` by default so chat-only providers
    don't need to care about them.
    """

    # ── chat (required) ──────────────────────────────────────────────

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Send messages to an LLM and return a structured response."""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        """Stream a chat completion as incremental chunks."""

    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model identifier for this provider."""

    # ── embedding (optional) ─────────────────────────────────────────

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts; returns one vector per text."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support embedding"
        )

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous version of :meth:`embed`."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support embedding"
        )

    def dimension(self) -> int:
        """Return the embedding vector dimension."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support embedding"
        )
