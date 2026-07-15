"""Deterministic LLM providers used by backend integration tests."""

from __future__ import annotations

import inspect
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import TypeAlias

from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_MEMORY_SUB_AGENT_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
    MEMORY_EMBED_BIZ_KEY,
    MEMORY_QUERY_PLANNER_BIZ_KEY,
    MEMORY_RERANK_BIZ_KEY,
)
from llm_client.types import LLMBizCatalog, LLMProvider, LLMProviderOption, LLMResponse, LLMUsage, ProviderChunk

CONFIG_PROVIDER_KEY = "config_chat"
STORY_PROVIDER_KEY = "story_chat"
SESSION_PROVIDER_KEY = "session_chat"

MAIN_PROVIDER_OPTIONS = (
    LLMProviderOption(CONFIG_PROVIDER_KEY, "openai", "config-model", 128_000),
    LLMProviderOption(STORY_PROVIDER_KEY, "openai", "story-model", 64_000),
    LLMProviderOption(SESSION_PROVIDER_KEY, "llama", "session-model", 8_192),
)


@dataclass(frozen=True)
class ProviderCall:
    messages: list[dict]
    tools: list[dict] | None
    stream: bool


@dataclass(frozen=True)
class ManagerCall:
    biz_key: str
    provider_key: str | None


ChatCallback: TypeAlias = Callable[
    [list[dict], list[dict] | None],
    LLMResponse | Awaitable[LLMResponse],
]
StreamResult: TypeAlias = Iterable[ProviderChunk]
StreamCallback: TypeAlias = Callable[
    [list[dict], list[dict] | None],
    StreamResult | Awaitable[StreamResult],
]
ChatAction: TypeAlias = LLMResponse | BaseException | ChatCallback
StreamAction: TypeAlias = StreamResult | BaseException | StreamCallback


def scripted_usage() -> LLMUsage:
    return LLMUsage(
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
        prompt_cache_hit_tokens=3,
    )


def response(
    content: str,
    *,
    model: str = "scripted-model",
    tool_calls: list[dict[str, object]] | None = None,
    finish_reason: str = "stop",
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        usage=scripted_usage(),
        model=model,
    )


def tool_call(name: str, arguments: str, *, call_id: str = "call_1") -> dict[str, object]:
    return {
        "id": call_id,
        "function": {
            "name": name,
            "arguments": arguments,
        },
    }


class ScriptedChatProvider(LLMProvider):
    """Queue-driven chat provider with deterministic fallback responses."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.calls: list[ProviderCall] = []
        self._chat_actions: deque[ChatAction] = deque()
        self._stream_actions: deque[StreamAction] = deque()

    def queue_chat(self, *actions: ChatAction) -> None:
        self._chat_actions.extend(actions)

    def queue_stream(self, *actions: StreamAction) -> None:
        self._stream_actions.extend(actions)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        frozen_messages = deepcopy(messages)
        frozen_tools = deepcopy(tools)
        self.calls.append(ProviderCall(frozen_messages, frozen_tools, False))
        action: ChatAction = (
            self._chat_actions.popleft()
            if self._chat_actions
            else response(f"{self.model} response", model=self.model)
        )
        if isinstance(action, BaseException):
            raise action
        if callable(action):
            result = action(frozen_messages, frozen_tools)
            if inspect.isawaitable(result):
                result = await result
            return result
        return action

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ):
        frozen_messages = deepcopy(messages)
        frozen_tools = deepcopy(tools)
        self.calls.append(ProviderCall(frozen_messages, frozen_tools, True))
        action: StreamAction = (
            self._stream_actions.popleft()
            if self._stream_actions
            else (
                ProviderChunk(content=f"{self.model} streamed"),
                ProviderChunk(
                    finish_reason="stop",
                    usage=scripted_usage(),
                    model=self.model,
                ),
            )
        )
        if isinstance(action, BaseException):
            raise action
        if callable(action):
            result = action(frozen_messages, frozen_tools)
            if inspect.isawaitable(result):
                result = await result
            action = result
        for chunk in action:
            yield chunk

    def get_default_model(self) -> str:
        return self.model


class ScriptedEmbeddingProvider(LLMProvider):
    """Small deterministic embedding provider for the real memory stack."""

    def __init__(self, dimension: int = 3) -> None:
        self._dimension = dimension
        self.calls: list[list[str]] = []

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        del messages, tools
        raise AssertionError("embedding provider must not be used for chat")

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None):
        del messages, tools
        raise AssertionError("embedding provider must not be used for streaming chat")
        yield

    def get_default_model(self) -> str:
        return "scripted-embedding"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embed_sync(texts)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def dimension(self) -> int:
        return self._dimension

    def _vector(self, text: str) -> list[float]:
        seed = sum(ord(char) for char in text)
        return [((seed + index * 17) % 101) / 100 for index in range(self._dimension)]


class ScriptedLLMManager:
    """Route real business keys to deterministic providers and record routing."""

    def __init__(self) -> None:
        self.main = {
            CONFIG_PROVIDER_KEY: ScriptedChatProvider("config-model"),
            STORY_PROVIDER_KEY: ScriptedChatProvider("story-model"),
            SESSION_PROVIDER_KEY: ScriptedChatProvider("session-model"),
        }
        self.status = ScriptedChatProvider("status-model")
        self.memory = ScriptedChatProvider("memory-model")
        self.planner = ScriptedChatProvider("planner-model")
        self.rerank = ScriptedChatProvider("rerank-model")
        self.embedding = ScriptedEmbeddingProvider()
        self.calls: list[ManagerCall] = []

    def get_provider(
        self,
        biz_key: str,
        *,
        provider_key: str | None = None,
    ) -> LLMProvider:
        self.calls.append(ManagerCall(biz_key, provider_key))
        if biz_key == AGENT_MAIN_BIZ_KEY:
            return self.main[provider_key or CONFIG_PROVIDER_KEY]
        providers: dict[str, LLMProvider] = {
            AGENT_STATUS_SUB_AGENT_BIZ_KEY: self.status,
            AGENT_MEMORY_SUB_AGENT_BIZ_KEY: self.memory,
            MEMORY_EMBED_BIZ_KEY: self.embedding,
            MEMORY_QUERY_PLANNER_BIZ_KEY: self.planner,
            MEMORY_RERANK_BIZ_KEY: self.rerank,
        }
        return providers[biz_key]

    def get_catalog(self, biz_key: str) -> LLMBizCatalog:
        if biz_key != AGENT_MAIN_BIZ_KEY:
            raise KeyError(biz_key)
        return LLMBizCatalog(
            biz_key=biz_key,
            kind="chat",
            default_provider_key=CONFIG_PROVIDER_KEY,
            options=MAIN_PROVIDER_OPTIONS,
        )

    def main_provider(self, provider_key: str = CONFIG_PROVIDER_KEY) -> ScriptedChatProvider:
        return self.main[provider_key]
