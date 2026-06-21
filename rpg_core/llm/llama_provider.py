"""LLMProvider adapter for local llama.cpp completion models."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from loguru import logger

from rpg_world.rpg_core.llama_service import LlamaEmbeddingModel
from rpg_world.rpg_core.llama_service.client import LlamaCompletionModel
from rpg_world.rpg_core.llm.base_provider import LLMProvider
from rpg_world.rpg_core.llm.types import LLMResponse, ProviderChunk

_TAG = "[LlamaCompletionProvider]"


class LlamaCompletionProvider(LLMProvider):
    """OpenAI-style provider wrapper over the process-isolated llama service."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
        request_timeout_ms: int = 60000,
        max_tokens: int = 512,
        temperature: float = 0.0,
        model: LlamaCompletionModel | None = None,
    ) -> None:
        self._model_path = str(Path(model_path))
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._model = model or LlamaCompletionModel(
            self._model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            request_timeout_ms=request_timeout_ms,
        )

    def get_default_model(self) -> str:
        return self._model_path

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        prompt = _build_prompt(messages, tools)
        raw = await asyncio.to_thread(
            self._model.complete,
            prompt,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        content = _extract_completion_text(raw).strip()

        if not tools:
            return LLMResponse(
                content=content,
                tool_calls=None,
                finish_reason="stop",
                model=self._model_path,
            )

        tool_calls = _parse_tool_calls(content, tools)
        finish_reason = "tool_calls" if tool_calls else "stop"
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=self._model_path,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        if tools:
            response = await self.chat(messages, tools=tools)
            yield ProviderChunk(
                content=response.content,
                tool_calls=response.tool_calls,
                finish_reason=response.finish_reason,
                usage=response.usage,
                model=response.model,
                request_id=response.request_id,
                created=response.created,
            )
            return

        prompt = _build_prompt(messages, tools)
        queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _produce() -> None:
            try:
                for content in self._model.complete_stream(
                    prompt,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, content)
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except BaseException as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)

        thread = threading.Thread(
            target=_produce,
            name="llama-provider-stream",
            daemon=True,
        )
        thread.start()

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            content = item
            yield ProviderChunk(content=content, model=self._model_path)
        yield ProviderChunk(
            finish_reason="stop",
            model=self._model_path,
        )


def _build_prompt(messages: list[dict], tools: list[dict] | None) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").upper()
        content = str(message.get("content") or "")
        parts.append(f"{role}:\n{content}")

    if tools:
        parts.append(
            "TOOLS:\n"
            f"{json.dumps(tools, ensure_ascii=False)}\n\n"
            "When a tool is needed, output only strict JSON in this shape:\n"
            '{"tool":"function_name","arguments":{...}}\n'
            "Do not wrap the JSON in Markdown. Do not include extra prose."
        )
    parts.append("ASSISTANT:")
    return "\n\n".join(parts)


def _extract_completion_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        choices = raw.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str):
                    return text
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
        for key in ("content", "text"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
    return str(raw)


def _parse_tool_calls(content: str, tools: list[dict]) -> list[dict[str, object]] | None:
    if not content.strip():
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.warning(_TAG + " failed to parse tool JSON: {}", exc)
        return None

    if not isinstance(parsed, dict):
        logger.warning(_TAG + " tool JSON is not an object")
        return None

    first_name = _first_tool_name(tools)
    requested_name = parsed.get("tool")
    name = str(requested_name) if requested_name else first_name
    if not name:
        logger.warning(_TAG + " no tool name available for parsed JSON")
        return None

    arguments = parsed.get("arguments", parsed)
    if not isinstance(arguments, dict):
        logger.warning(_TAG + " tool arguments are not an object")
        return None

    return [
        {
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            },
        }
    ]


def _first_tool_name(tools: list[dict]) -> str:
    for schema in tools:
        function = schema.get("function") if isinstance(schema, dict) else None
        if isinstance(function, dict) and function.get("name"):
            return str(function["name"])
    return ""


class LlamaEmbeddingProvider(LLMProvider):
    """LLMProvider over a process-isolated llama.cpp embedding model.

    Only embedding methods are supported; chat methods raise
    ``NotImplementedError``.
    """

    def __init__(
        self,
        *,
        model_path: str | Path,
        n_ctx: int = 32768,
        n_gpu_layers: int = 0,
        n_threads: int = 4,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        model: LlamaEmbeddingModel | None = None,
    ) -> None:
        self._model_path = str(Path(model_path))
        self._model = model or LlamaEmbeddingModel(
            self._model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )
        self._dim = self._model.dimension()
        if self._dim == 0:
            raise RuntimeError(
                f"LlamaEmbeddingProvider: model returned zero-dimension vectors "
                f"({self._model_path!r})"
            )

    # ── chat — not supported ────────────────────────────────────────

    async def chat(self, messages, tools=None):
        raise NotImplementedError(
            "LlamaEmbeddingProvider does not support chat"
        )

    async def chat_stream(self, messages, tools=None):
        raise NotImplementedError(
            "LlamaEmbeddingProvider does not support chat"
        )

    def get_default_model(self) -> str:
        return self._model_path

    # ── embedding ───────────────────────────────────────────────────

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self.embed_sync, texts)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._model.embed(texts)

    def dimension(self) -> int:
        return self._dim
