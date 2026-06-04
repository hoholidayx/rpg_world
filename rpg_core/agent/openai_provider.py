"""Thin wrapper around ``openai.AsyncOpenAI`` for text-only send-reply.

Supports optional tool/function calling via the ``tools`` parameter.
Implements the ``LLMProvider`` ABC.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from openai import AsyncOpenAI

from rpg_world.rpg_core.agent.base_provider import LLMProvider


class OpenAIProvider(LLMProvider):
    """Minimal OpenAI chat completion provider.

    Supports both plain-text and tool-call responses.  When *tools* is
    provided, the returned dict may contain ``"tool_calls"``.

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
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url,
            http_client=http_client,
        )

    def get_default_model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Send *messages* to the model and return a result dict.

        Args:
            messages: OpenAI-format message list.
            tools: Optional list of OpenAI tool/function schemas.

        Returns:
            A dict with keys:
                ``content`` — text content (may be empty when tool_calls present)
                ``tool_calls`` — list of OpenAI tool-call dicts, or ``None``
                ``finish_reason`` — ``"stop"``, ``"tool_calls"``, etc.

        Raises ``openai.OpenAIError`` on API / network errors.
        """
        kwargs: dict = {"model": self._model, "messages": messages}
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if tools is not None:
            kwargs["tools"] = tools

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        result: dict[str, Any] = {
            "content": msg.content or "",
            "tool_calls": None,
            "finish_reason": choice.finish_reason,
        }

        if msg.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in msg.tool_calls]

        return result
