"""Context/turn usage snapshots for UI-facing diagnostics.

These structures are transport helpers only. They are intentionally not tied to
the persisted RPG context model so usage can be stored later without changing
the current session history shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol, Sequence

from llm_service.types import LLMUsage

ContextUsageSource = Literal["provider_usage", "context_preview", "fallback_estimate", "unavailable"]
ContextUsageAccuracy = Literal["accurate", "estimated", "unknown"]


class UsageCallRecord(Protocol):
    """Minimal call-record shape required for usage aggregation."""

    model: str
    usage: LLMUsage | None


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ContextUsageSnapshot:
    """Normalized usage snapshot shared by context preview and turn usage."""

    used_tokens: int | None
    context_limit: int | None
    source: ContextUsageSource
    accuracy: ContextUsageAccuracy
    prompt_tokens: int | None = None
    completion_tokens: int = 0
    total_tokens: int | None = None
    cached_tokens: int = 0
    model: str | None = None
    finish_reason: str | None = None
    duration_ms: float | None = None
    created_at: str = field(default_factory=utc_now_iso)
    error_reason: str | None = None

    def to_camel_payload(self) -> dict[str, object]:
        """Return context metadata; ratio/status are intentionally UI-owned."""
        prompt_tokens = self.prompt_tokens if self.prompt_tokens is not None else self.used_tokens
        total_tokens = self.total_tokens
        if total_tokens is None and self.used_tokens is not None:
            total_tokens = self.used_tokens + max(0, int(self.completion_tokens or 0))
        return {
            "usedTokens": self.used_tokens,
            "promptTokens": prompt_tokens,
            "completionTokens": self.completion_tokens,
            "totalTokens": total_tokens,
            "cachedTokens": self.cached_tokens,
            "contextLimit": self.context_limit,
            "source": self.source,
            "accuracy": self.accuracy,
            "model": self.model,
            "finishReason": self.finish_reason,
            "durationMs": self.duration_ms,
            "createdAt": self.created_at,
            "errorReason": self.error_reason,
        }


def aggregate_usage_records(calls: Sequence[UsageCallRecord]) -> LLMUsage | None:
    """Aggregate provider usage records collected during one turn."""
    if not calls:
        return None
    usages = [call.usage for call in calls if call.usage is not None]
    if not usages:
        return None

    total_prompt = sum(usage.prompt_tokens for usage in usages)
    total_completion = sum(usage.completion_tokens for usage in usages)
    total_cached = sum(usage.cached_tokens for usage in usages)
    total_missed = sum(usage.prompt_cache_miss_tokens for usage in usages)
    if total_prompt <= 0 and total_completion <= 0 and total_cached <= 0:
        return None

    return LLMUsage(
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
        total_tokens=total_prompt + total_completion,
        prompt_tokens_details={"cached_tokens": total_cached} if total_cached else None,
        prompt_cache_hit_tokens=total_cached,
        prompt_cache_miss_tokens=total_missed,
    )


def usage_to_wire_payload(
    usage: LLMUsage,
    *,
    model: str | None = None,
    finish_reason: str | None = None,
    duration_ms: float | None = None,
    created_at: str | None = None,
) -> dict[str, object]:
    """Return backward-compatible turn usage metadata for API/SSE payloads."""
    raw_usage = usage.raw_usage if isinstance(usage.raw_usage, dict) else {}
    raw_source = _raw_string(raw_usage.get("source")) or "provider_usage"
    raw_accuracy = _raw_string(raw_usage.get("accuracy")) or "accurate"
    raw_created_at = _raw_string(raw_usage.get("createdAt"))
    payload: dict[str, object] = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "cached_tokens": usage.cached_tokens,
        "source": raw_source,
        "accuracy": raw_accuracy,
        "createdAt": created_at or raw_created_at or utc_now_iso(),
    }
    if model:
        payload["model"] = model
    if finish_reason:
        payload["finishReason"] = finish_reason
    if duration_ms is not None:
        payload["durationMs"] = duration_ms
    return payload


def usage_payload_from_records(
    calls: Sequence[UsageCallRecord],
    *,
    duration_ms: float | None = None,
    model: str | None = None,
    finish_reason: str | None = None,
) -> dict[str, object] | None:
    """Aggregate calls and serialize usage without depending on Agent types."""
    usage = aggregate_usage_records(calls)
    if usage is None:
        return None
    return usage_to_wire_payload(
        usage,
        model=model or _last_model(calls),
        finish_reason=finish_reason,
        duration_ms=duration_ms,
    )


def _last_model(calls: Sequence[UsageCallRecord]) -> str | None:
    for call in reversed(calls):
        if call.model:
            return call.model
    return None


def _raw_string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
