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
from rpg_world.rpg_core.agent.types import LLMResponse, LLMUsage


class OpenAIProvider(LLMProvider):
    """Minimal OpenAI chat completion provider.

    Supports both plain-text and tool-call responses.
    Captures usage / model / reasoning metadata from API responses.

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
    ) -> LLMResponse:
        """Send *messages* to the model and return a structured ``LLMResponse``.

        Captures ``usage``, ``model``, ``request_id``, ``created`` timestamp
        and ``reasoning_content`` from the API response when available.

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

        # ── usage ────────────────────────────────────────────────────
        usage: LLMUsage | None = None
        if response.usage is not None:
            raw = response.usage
            usage = LLMUsage(
                prompt_tokens=raw.prompt_tokens or 0,
                completion_tokens=raw.completion_tokens or 0,
                total_tokens=raw.total_tokens or 0,
                prompt_tokens_details=(
                    dict(raw.prompt_tokens_details)
                    if raw.prompt_tokens_details else None
                ),
                completion_tokens_details=(
                    dict(raw.completion_tokens_details)
                    if raw.completion_tokens_details else None
                ),
            )

        # ── reasoning / thinking ─────────────────────────────────────
        reasoning_content: str | None = None
        if hasattr(msg, "reasoning_content"):
            reasoning_content = msg.reasoning_content
        if not reasoning_content and hasattr(msg, "reasoning"):
            reasoning_content = msg.reasoning

        # ── tool_calls ───────────────────────────────────────────────
        tool_calls: list[dict[str, Any]] | None = None
        if msg.tool_calls:
            tool_calls = [tc.to_dict() for tc in msg.tool_calls]

        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            model=getattr(response, "model", None) or self._model,
            request_id=getattr(response, "id", None),
            created=getattr(response, "created", None),
            reasoning_content=reasoning_content,
        )
