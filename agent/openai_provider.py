"""Thin wrapper around ``openai.AsyncOpenAI`` for text-only send-reply."""

from __future__ import annotations

import os
from typing import Any

import httpx
from openai import AsyncOpenAI


class OpenAIProvider:
    """Minimal OpenAI chat completion provider.

    No streaming, no tool calls — pure text generation for the MVP.

    If your environment has a proxy that ``httpx`` cannot handle
    (e.g. ``socks://``), pass ``http_client=httpx.AsyncClient(proxy=None)``
    to bypass environment proxy detection.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url,
            http_client=http_client,
        )

    async def chat(self, messages: list[dict]) -> str:
        """Send *messages* to the model and return the assistant text reply.

        Raises ``openai.OpenAIError`` on API / network errors.
        """
        kwargs: dict = {"model": self.model, "messages": messages}
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature

        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
