"""Wire conversion helpers for the public LLM client contract."""

from __future__ import annotations

from collections.abc import Mapping

from llm_client.types import DocumentScore, LLMBizCatalog, LLMProviderOption, LLMResponse, LLMUsage, ProviderChunk


def usage_from_wire(value: object) -> LLMUsage | None:
    if not isinstance(value, Mapping):
        return None
    return LLMUsage(
        prompt_tokens=int(value.get("promptTokens", 0) or 0),
        completion_tokens=int(value.get("completionTokens", 0) or 0),
        total_tokens=int(value.get("totalTokens", 0) or 0),
        prompt_tokens_details=_dict_or_none(value.get("promptTokensDetails")),
        completion_tokens_details=_dict_or_none(value.get("completionTokensDetails")),
        prompt_cache_hit_tokens=int(value.get("promptCacheHitTokens", 0) or 0),
        prompt_cache_miss_tokens=int(value.get("promptCacheMissTokens", 0) or 0),
        raw_usage=_dict_or_none(value.get("rawUsage")),
    )


def usage_to_wire(value: LLMUsage | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "promptTokens": value.prompt_tokens,
        "completionTokens": value.completion_tokens,
        "totalTokens": value.total_tokens,
        "promptTokensDetails": value.prompt_tokens_details,
        "completionTokensDetails": value.completion_tokens_details,
        "promptCacheHitTokens": value.prompt_cache_hit_tokens,
        "promptCacheMissTokens": value.prompt_cache_miss_tokens,
        "rawUsage": value.raw_usage,
    }


def response_from_wire(value: Mapping[str, object]) -> LLMResponse:
    tool_calls = value.get("toolCalls")
    return LLMResponse(
        content=str(value.get("content") or ""),
        tool_calls=list(tool_calls) if isinstance(tool_calls, list) else None,
        finish_reason=_optional_str(value.get("finishReason")),
        usage=usage_from_wire(value.get("usage")),
        model=_optional_str(value.get("model")),
        request_id=_optional_str(value.get("requestId")),
        created=_optional_int(value.get("created")),
        reasoning_content=_optional_str(value.get("reasoningContent")),
    )


def response_to_wire(value: LLMResponse) -> dict[str, object]:
    return {
        "content": value.content,
        "toolCalls": value.tool_calls,
        "finishReason": value.finish_reason,
        "usage": usage_to_wire(value.usage),
        "model": value.model,
        "requestId": value.request_id,
        "created": value.created,
        "reasoningContent": value.reasoning_content,
    }


def chunk_from_wire(value: Mapping[str, object]) -> ProviderChunk:
    tool_calls = value.get("toolCalls")
    return ProviderChunk(
        content=str(value.get("content") or ""),
        reasoning_content=_optional_str(value.get("reasoningContent")),
        tool_calls=list(tool_calls) if isinstance(tool_calls, list) else None,
        finish_reason=_optional_str(value.get("finishReason")),
        usage=usage_from_wire(value.get("usage")),
        model=_optional_str(value.get("model")),
        request_id=_optional_str(value.get("requestId")),
        created=_optional_int(value.get("created")),
    )


def chunk_to_wire(value: ProviderChunk) -> dict[str, object]:
    return {
        "content": value.content,
        "reasoningContent": value.reasoning_content,
        "toolCalls": value.tool_calls,
        "finishReason": value.finish_reason,
        "usage": usage_to_wire(value.usage),
        "model": value.model,
        "requestId": value.request_id,
        "created": value.created,
    }


def catalog_from_wire(value: Mapping[str, object]) -> LLMBizCatalog:
    raw_options = value.get("options")
    if not isinstance(raw_options, list):
        raise ValueError("LLM catalog options must be a list")
    options = tuple(
        LLMProviderOption(
            provider_key=str(item.get("providerKey") or ""),
            backend=str(item.get("backend") or ""),
            model=str(item.get("model") or ""),
            context_window=_optional_int(item.get("contextWindow")),
            input_modalities=tuple(
                str(modality).strip().lower()
                for modality in item.get("inputModalities", ["text"])
                if str(modality).strip()
            ),
        )
        for item in raw_options
        if isinstance(item, Mapping)
    )
    return LLMBizCatalog(
        biz_key=str(value.get("bizKey") or ""),
        kind=str(value.get("kind") or ""),
        default_provider_key=str(value.get("defaultProviderKey") or ""),
        options=options,
    )


def scores_from_wire(value: object) -> list[DocumentScore]:
    if not isinstance(value, list):
        raise ValueError("LLM rerank scores must be a list")
    return [
        DocumentScore(
            score=float(item.get("score", 0.0) or 0.0),
            reason=str(item.get("reason") or ""),
            debug=dict(item.get("debug") or {}),
        )
        for item in value
        if isinstance(item, Mapping)
    ]


def _dict_or_none(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None
