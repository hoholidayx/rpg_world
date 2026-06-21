"""Thin wrapper around ``openai.AsyncOpenAI`` for chat completion + embedding."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
from loguru import logger
from openai import AsyncOpenAI

from rpg_world.rpg_core.llm.base_provider import LLMProvider
from rpg_world.rpg_core.llm.types import LLMResponse, LLMUsage, ProviderChunk
from rpg_world.rpg_core.settings import settings


def _build_usage(raw, raw_dict: dict[str, object] | None) -> LLMUsage | None:
    if raw is None:
        return None

    if raw_dict:
        hit = raw_dict.get("prompt_cache_hit_tokens", raw_dict.get("cache_read_input_tokens", 0))
        if raw_dict.get("prompt_tokens_details"):
            details_hit = raw_dict["prompt_tokens_details"].get("cached_tokens", 0)
            if not hit:
                hit = details_hit
        miss = raw_dict.get("prompt_cache_miss_tokens", raw_dict.get("prompt_tokens", 0) - hit)
    else:
        hit = 0
        if getattr(raw, "prompt_tokens_details", None):
            hit = getattr(raw.prompt_tokens_details, "cached_tokens", 0) or 0
        miss = 0

    if raw_dict:
        logger.info("[OpenAIProvider] raw usage: {}", raw_dict)

    return LLMUsage(
        prompt_tokens=raw.prompt_tokens or 0,
        completion_tokens=raw.completion_tokens or 0,
        total_tokens=raw.total_tokens or 0,
        prompt_tokens_details=(dict(raw.prompt_tokens_details) if raw.prompt_tokens_details else None),
        completion_tokens_details=(dict(raw.completion_tokens_details) if raw.completion_tokens_details else None),
        prompt_cache_hit_tokens=hit,
        prompt_cache_miss_tokens=miss,
        raw_usage=raw_dict,
    )


class OpenAIProvider(LLMProvider):
    """Minimal OpenAI chat completion provider."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        http_client: httpx.AsyncClient | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._dimension: int | None = None
        self._api_key = settings.get_openai_api_key(api_key)
        self._base_url = base_url
        self._http_client = http_client

        if client is not None:
            self._client = client
            return

        client_kwargs: dict[str, object] = {
            "api_key": self._api_key,
            "base_url": self._base_url,
        }
        if self._http_client is not None:
            client_kwargs["http_client"] = self._http_client
        self._client = AsyncOpenAI(**client_kwargs)

    def get_default_model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
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

        raw_dict: dict[str, object] | None = None
        if response.usage is not None:
            try:
                raw = response.usage
                raw_dict = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)
            except Exception:
                raw_dict = None
        usage = _build_usage(response.usage, raw_dict)

        reasoning_content: str | None = None
        if hasattr(msg, "reasoning_content"):
            reasoning_content = msg.reasoning_content
        if not reasoning_content and hasattr(msg, "reasoning"):
            reasoning_content = msg.reasoning

        tool_calls: list[dict[str, object]] | None = None
        if getattr(msg, "tool_calls", None):
            tool_calls = [tc.to_dict() for tc in msg.tool_calls]

        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            finish_reason=getattr(choice, "finish_reason", None),
            usage=usage,
            model=getattr(response, "model", None) or self._model,
            request_id=getattr(response, "id", None),
            created=getattr(response, "created", None),
            reasoning_content=reasoning_content,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via the OpenAI-compatible embeddings API."""
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        vectors = [list(item.embedding) for item in response.data]
        if vectors and self._dimension is None:
            self._dimension = len(vectors[0])
        return vectors

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous version of :meth:`embed`."""
        if not texts:
            return []
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.embed(texts))

        # Event loop already running — bridge via thread
        import threading

        result: dict[str, list[list[float]]] = {}
        exc: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(self.embed(texts))
            except BaseException as e:
                exc["err"] = e

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "err" in exc:
            raise exc["err"]
        return result["value"]

    def dimension(self) -> int:
        """Return the embedding vector dimension (lazy-probed)."""
        if self._dimension is not None:
            return self._dimension
        vectors = self.embed_sync(["dimension probe"])
        return len(vectors[0]) if vectors else 0

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
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
        tool_call_acc: dict[int, dict] = {}

        async for raw_chunk in stream:
            choice = raw_chunk.choices[0] if raw_chunk.choices else None
            usage: LLMUsage | None = None
            if raw_chunk.usage is not None:
                raw_dict: dict[str, object] | None = None
                try:
                    raw_dict = raw_chunk.usage.to_dict() if hasattr(raw_chunk.usage, "to_dict") else dict(raw_chunk.usage)
                except Exception:
                    raw_dict = None
                usage = _build_usage(raw_chunk.usage, raw_dict)

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

            tool_calls: list[dict] | None = None
            if finish_reason and tool_call_acc:
                tool_calls = [tool_call_acc[i] for i in sorted(tool_call_acc)]

            if not choice and not usage:
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
