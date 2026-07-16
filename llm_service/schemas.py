"""HTTP schemas for the standalone LLM service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WireModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class LLMHealthResponse(WireModel):
    status: str
    config_loaded: bool = Field(alias="configLoaded")


class LLMProviderOptionResponse(WireModel):
    provider_key: str = Field(alias="providerKey")
    backend: str
    model: str
    context_window: int | None = Field(default=None, alias="contextWindow")
    input_modalities: list[str] = Field(default_factory=lambda: ["text"], alias="inputModalities")


class LLMCatalogResponse(WireModel):
    biz_key: str = Field(alias="bizKey")
    kind: str
    default_provider_key: str = Field(alias="defaultProviderKey")
    options: list[LLMProviderOptionResponse]


class LLMChatRequest(WireModel):
    biz_key: str = Field(alias="bizKey", min_length=1)
    provider_key: str | None = Field(default=None, alias="providerKey")
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None


class LLMUsageResponse(WireModel):
    prompt_tokens: int = Field(default=0, alias="promptTokens")
    completion_tokens: int = Field(default=0, alias="completionTokens")
    total_tokens: int = Field(default=0, alias="totalTokens")
    prompt_tokens_details: dict[str, Any] | None = Field(default=None, alias="promptTokensDetails")
    completion_tokens_details: dict[str, Any] | None = Field(default=None, alias="completionTokensDetails")
    prompt_cache_hit_tokens: int = Field(default=0, alias="promptCacheHitTokens")
    prompt_cache_miss_tokens: int = Field(default=0, alias="promptCacheMissTokens")
    raw_usage: dict[str, Any] | None = Field(default=None, alias="rawUsage")


class LLMChatResponse(WireModel):
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = Field(default=None, alias="toolCalls")
    finish_reason: str | None = Field(default=None, alias="finishReason")
    usage: LLMUsageResponse | None = None
    model: str | None = None
    request_id: str | None = Field(default=None, alias="requestId")
    created: int | None = None
    reasoning_content: str | None = Field(default=None, alias="reasoningContent")


class LLMEmbeddingRequest(WireModel):
    biz_key: str = Field(alias="bizKey", min_length=1)
    provider_key: str | None = Field(default=None, alias="providerKey")
    texts: list[str]


class LLMEmbeddingResponse(WireModel):
    vectors: list[list[float]]


class LLMEmbeddingDimensionResponse(WireModel):
    dimension: int = Field(ge=0)


class LLMRerankRequest(WireModel):
    biz_key: str = Field(alias="bizKey", min_length=1)
    provider_key: str | None = Field(default=None, alias="providerKey")
    query: str
    documents: list[str]


class LLMDocumentScoreResponse(WireModel):
    score: float
    reason: str = ""
    debug: dict[str, Any] = Field(default_factory=dict)


class LLMRerankResponse(WireModel):
    scores: list[LLMDocumentScoreResponse]


class LLMSpeechRequest(WireModel):
    biz_key: str = Field(alias="bizKey", min_length=1)
    provider_key: str | None = Field(default=None, alias="providerKey")
    text: str = Field(min_length=1, max_length=4096)


class LLMSpeechProfileResponse(WireModel):
    biz_key: str = Field(alias="bizKey")
    provider_key: str = Field(alias="providerKey")
    model: str
    voice: str
    response_format: str = Field(alias="responseFormat")
    speed: float
    cache_revision: str = Field(alias="cacheRevision")
    config_fingerprint: str = Field(alias="configFingerprint")
