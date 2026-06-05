"""Thin wrapper around ``openai.AsyncOpenAI`` for text-only send-reply.

Supports optional tool/function calling via the ``tools`` parameter.
Implements the ``LLMProvider`` ABC.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from openai import AsyncOpenAI

from rpg_world.rpg_core.agent.base_provider import LLMProvider
from rpg_world.rpg_core.agent.agent_types import LLMResponse, LLMUsage, ProviderChunk


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

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        """Stream response chunks from the OpenAI API.

        Yields one ``ProviderChunk`` per API response chunk.  The caller
        is responsible for accumulating content and tool-call deltas.
        """
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if tools is not None:
            kwargs["tools"] = tools

        stream = await self._client.chat.completions.create(**kwargs)

        # Accumulate tool call deltas across chunks
        tool_call_acc: dict[int, dict] = {}

        async for raw_chunk in stream:
            choice = raw_chunk.choices[0] if raw_chunk.choices else None

            # usage may appear on the final chunk
            usage: LLMUsage | None = None
            if raw_chunk.usage is not None:
                u = raw_chunk.usage
                usage = LLMUsage(
                    prompt_tokens=u.prompt_tokens or 0,
                    completion_tokens=u.completion_tokens or 0,
                    total_tokens=u.total_tokens or 0,
                    prompt_tokens_details=(
                        dict(u.prompt_tokens_details) if u.prompt_tokens_details else None
                    ),
                    completion_tokens_details=(
                        dict(u.completion_tokens_details) if u.completion_tokens_details else None
                    ),
                )

            content_delta = ""
            reasoning_delta: str | None = None
            finish_reason: str | None = None

            if choice:
                delta = choice.delta
                if delta.content:
                    content_delta = delta.content
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_delta = delta.reasoning_content
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_acc:
                            tool_call_acc[idx] = {
                                "id": tc_delta.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        acc = tool_call_acc[idx]
                        if tc_delta.id:
                            acc["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                acc["function"]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                acc["function"]["arguments"] += tc_delta.function.arguments
                finish_reason = choice.finish_reason

            # On the last chunk (or any chunk with finish_reason), emit accumulated tool calls
            tool_calls: list[dict] | None = None
            if finish_reason and tool_call_acc:
                tool_calls = [tool_call_acc[i] for i in sorted(tool_call_acc)]

            # Usage may come on a standalone chunk with no choices
            if not choice and not usage:
                # Skip usage-only chunks (OpenAI sends these as separate events)
                continue

            yield ProviderChunk(
                content=content_delta,
                reasoning_content=reasoning_delta,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage,
                model=getattr(raw_chunk, "model", None) or self._model,
                request_id=getattr(raw_chunk, "id", None),
                created=getattr(raw_chunk, "created", None),
            )
