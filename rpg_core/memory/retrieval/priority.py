"""Memory candidate source priority helpers.

This module keeps source/granularity preference out of HybridRetriever so
future storage sources can expose the same semantic metadata without changing
retrieval orchestration code.
"""

from __future__ import annotations

from typing import Any

DEFAULT_GRANULARITY_SCORES: dict[str, float] = {
    "batch": 1.00,
    "event": 0.95,
    "session": 0.70,
    "global": 0.55,
    "unknown": 0.80,
}

_ALIASES: dict[str, str] = {
    "batch": "batch",
    "event": "event",
    "session": "session",
    "global": "global",
    "overall": "global",
    "summary": "batch",
}


def resolve_memory_granularity(metadata: dict[str, Any]) -> str:
    explicit = _normalize(metadata.get("memory_granularity") or metadata.get("granularity"))
    if explicit:
        return explicit

    semantic_type = _normalize(metadata.get("type"))
    if semantic_type:
        return semantic_type

    if metadata.get("batch_id") is not None:
        return "batch"
    return "unknown"


def granularity_score(metadata: dict[str, Any], scores: dict[str, float] | None = None) -> tuple[str, float]:
    granularity = resolve_memory_granularity(metadata)
    score_map = scores or DEFAULT_GRANULARITY_SCORES
    return granularity, float(score_map.get(granularity, score_map["unknown"]))


def _normalize(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return _ALIASES.get(text, text)
