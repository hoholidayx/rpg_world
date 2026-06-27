"""Provider-level LLM response, streaming, and local-runtime types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = "JsonScalar | list[JsonValue] | dict[str, JsonValue]"
JsonObject: TypeAlias = dict[str, JsonValue]

LlamaModelConfig: TypeAlias = JsonObject
LlamaRequestParams: TypeAlias = JsonObject
LlamaResponsePayload: TypeAlias = JsonValue
LlamaModelHandle: TypeAlias = object
LlamaLogits: TypeAlias = object
LlamaCacheKeyPart: TypeAlias = JsonScalar
LlamaCacheKey: TypeAlias = tuple[LlamaCacheKeyPart, ...]


@dataclass
class LLMUsage:
    """Token usage returned by an LLM provider."""

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
            return self.prompt_tokens_details.get("cached_tokens", 0) or 0
        return 0

    @property
    def has_usage(self) -> bool:
        return self.total_tokens > 0 or self.prompt_tokens_details is not None

    def __str__(self) -> str:
        parts = [f"{self.prompt_tokens}p + {self.completion_tokens}c = {self.total_tokens}t"]
        cached = self.cached_tokens
        if cached:
            parts.append(f" [cache: {cached} hit]")
        return "".join(parts)


@dataclass
class LLMResponse:
    """Structured response returned by ``LLMProvider.chat()``."""

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
    """Provider-level streaming delta chunk."""

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
    """Normalized score for one generic document rerank candidate."""

    score: float
    reason: str = ""
    debug: JsonObject = field(default_factory=dict)

    @property
    def clamped_score(self) -> float:
        return max(0.0, min(1.0, float(self.score)))
