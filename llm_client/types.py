"""Provider-neutral DTOs and protocols shared by LLM service clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from commons.types import JsonObject


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_tokens_details: dict[str, object] | None = None
    completion_tokens_details: dict[str, object] | None = None
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0
    raw_usage: dict[str, object] | None = None

    @property
    def cached_tokens(self) -> int:
        if self.prompt_cache_hit_tokens:
            return self.prompt_cache_hit_tokens
        if self.prompt_tokens_details:
            return int(self.prompt_tokens_details.get("cached_tokens", 0) or 0)
        return 0

    @property
    def has_usage(self) -> bool:
        return self.total_tokens > 0 or self.prompt_tokens_details is not None

    def __str__(self) -> str:
        text = f"{self.prompt_tokens}p + {self.completion_tokens}c = {self.total_tokens}t"
        cached = self.cached_tokens
        return f"{text} [cache: {cached} hit]" if cached else text


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict[str, object]] | None
    finish_reason: str | None
    usage: LLMUsage | None = None
    model: str | None = None
    request_id: str | None = None
    created: int | None = None
    reasoning_content: str | None = None


@dataclass
class ProviderChunk:
    content: str = ""
    reasoning_content: str | None = None
    tool_calls: list[dict] | None = None
    finish_reason: str | None = None
    usage: LLMUsage | None = None
    model: str | None = None
    request_id: str | None = None
    created: int | None = None


@dataclass(frozen=True)
class DocumentScore:
    score: float
    reason: str = ""
    debug: JsonObject = field(default_factory=dict)

    @property
    def clamped_score(self) -> float:
        return max(0.0, min(1.0, float(self.score)))


@dataclass(frozen=True)
class LLMProviderOption:
    provider_key: str
    backend: str
    model: str
    context_window: int | None


@dataclass(frozen=True)
class LLMBizCatalog:
    biz_key: str
    kind: str
    default_provider_key: str
    options: tuple[LLMProviderOption, ...]

    def option(self, provider_key: str | None = None) -> LLMProviderOption:
        selected = provider_key or self.default_provider_key
        for option in self.options:
            if option.provider_key == selected:
                return option
        raise ValueError(f"provider_key {selected!r} is not available for {self.biz_key!r}")


class EmbeddingProviderError(Exception):
    """Raised when an embedding request cannot be fulfilled."""


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        raise NotImplementedError

    @abstractmethod
    def get_default_model(self) -> str:
        raise NotImplementedError

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def dimension(self) -> int:
        raise NotImplementedError


class DocumentScoreProvider(ABC):
    @abstractmethod
    async def score_documents(
        self,
        query: str,
        documents: list[str],
    ) -> list[DocumentScore]:
        raise NotImplementedError
