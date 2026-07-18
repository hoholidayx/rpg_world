"""LLMProvider adapter for local llama.cpp completion models."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from loguru import logger

from llm_client.types import (
    DocumentScore,
    DocumentScoreProvider,
    LLMProvider,
    LLMResponse,
    ProviderChunk,
)
from llm_service.errors import LLMInputModalityUnsupportedError
from llm_service.runtime import (
    DirectLlamaCompletionModel,
    DirectLlamaEmbeddingModel,
    DirectLlamaRerankModel,
    LlamaRuntimeTimeoutError,
)

_TAG = "[LlamaCompletionProvider]"

DEFAULT_QWEN_RERANK_INSTRUCTION = (
    "Given a user query, judge whether the candidate document is relevant and useful for answering it."
)


class LlamaCompletionProvider(LLMProvider):
    """OpenAI-style provider wrapper over this service's direct llama runtime."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
        request_timeout_ms: int = 60000,
        max_tokens: int = 512,
        temperature: float = 0.0,
        model: DirectLlamaCompletionModel | None = None,
    ) -> None:
        self._model_path = str(Path(model_path))
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._request_timeout_seconds = max(1, int(request_timeout_ms)) / 1000.0
        self._model = model or DirectLlamaCompletionModel(
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
        _reject_image_input(messages)
        prompt = _build_prompt(messages, tools)
        raw = await self._model.complete_async(
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
        _reject_image_input(messages)
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

        def _enqueue(item: str | BaseException | None) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, item)
            except RuntimeError:
                # The request loop may already be closed during service shutdown.
                pass

        cancelled = threading.Event()
        future = self._model.start_complete_stream(
            prompt,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            stop=None,
            on_chunk=_enqueue,
            cancelled=cancelled,
        )

        def _finished(completed) -> None:  # noqa: ANN001
            try:
                completed.result()
            except BaseException as exc:
                _enqueue(exc)
            else:
                _enqueue(None)

        future.add_done_callback(_finished)

        try:
            try:
                async with asyncio.timeout(self._request_timeout_seconds):
                    while True:
                        item = await queue.get()
                        if item is None:
                            break
                        if isinstance(item, BaseException):
                            raise item
                        content = item
                        yield ProviderChunk(content=content, model=self._model_path)
            except TimeoutError as exc:
                raise LlamaRuntimeTimeoutError(
                    "llama runtime stream timed out"
                ) from exc
        finally:
            cancelled.set()
            future.cancel()
        yield ProviderChunk(
            finish_reason="stop",
            model=self._model_path,
        )


def _build_prompt(messages: list[dict], tools: list[dict] | None) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").upper()
        content = _text_content(message.get("content"))
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


def _reject_image_input(messages: list[dict]) -> None:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if any(isinstance(part, dict) and part.get("type") == "image_url" for part in content):
            raise LLMInputModalityUnsupportedError("image", "llama")


def _text_content(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


def _extract_completion_text(raw: object) -> str:
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
    """LLMProvider over a service-owned llama.cpp embedding model.

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
        model: DirectLlamaEmbeddingModel | None = None,
    ) -> None:
        self._model_path = str(Path(model_path))
        self._model = model or DirectLlamaEmbeddingModel(
            self._model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )
        self._dim: int | None = None

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
        vectors = await self._model.embed_async(texts)
        self._remember_dimension(vectors)
        return vectors

    async def dimension(self) -> int:
        if self._dim is None:
            self._dim = await self._model.dimension_async()
        if self._dim <= 0:
            raise RuntimeError(
                "LlamaEmbeddingProvider: model returned zero-dimension vectors "
                f"({self._model_path!r})"
            )
        return self._dim

    def _remember_dimension(self, vectors: list[list[float]]) -> None:
        if vectors and self._dim is None:
            self._dim = len(vectors[0])


class LlamaLogitRerankProvider(LLMProvider, DocumentScoreProvider):
    """Generic document rerank provider backed by local yes/no logits."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        instruction: str = DEFAULT_QWEN_RERANK_INSTRUCTION,
        max_length: int | None = None,
        model: DirectLlamaRerankModel | None = None,
    ) -> None:
        self._model_path = str(Path(model_path))
        self._instruction = instruction or DEFAULT_QWEN_RERANK_INSTRUCTION
        self._max_length = max(1, int(max_length or n_ctx))
        self._model = model or DirectLlamaRerankModel(
            self._model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )

    def get_default_model(self) -> str:
        return self._model_path

    async def score_documents(self, query: str, documents: list[str]) -> list[DocumentScore]:
        raw_scores = await self._model.rerank_async(
            query,
            documents,
            instruction=self._instruction,
            max_length=self._max_length,
        )
        if len(raw_scores) != len(documents):
            raise ValueError(f"rerank score count mismatch: expected={len(documents)} got={len(raw_scores)}")
        results: list[DocumentScore] = []
        for raw in raw_scores:
            score = max(0.0, min(1.0, float(raw.get("score", 0.0))))
            yes_logit = float(raw.get("yes_logit", 0.0))
            no_logit = float(raw.get("no_logit", 0.0))
            results.append(
                DocumentScore(
                    score=score,
                    reason="yes/no logits",
                    debug={
                        "source": "logits",
                        "yes_logit": yes_logit,
                        "no_logit": no_logit,
                    },
                )
            )
        return results

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        raise NotImplementedError("LlamaLogitRerankProvider supports score_documents(), not chat()")

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None):
        raise NotImplementedError("LlamaLogitRerankProvider supports score_documents(), not chat_stream()")
