"""RP-specific eligibility and semantic priority for recall candidates."""

from __future__ import annotations

from collections.abc import Mapping

from commons.types import JsonValue

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


class RPRecallCandidatePolicy:
    """Keep derived aggregates out and prefer RP memory granularity."""

    def is_eligible(self, metadata: Mapping[str, object]) -> bool:
        if str(metadata.get("type", "")).strip().lower() == "overall":
            return False
        file_path = str(metadata.get("file", "") or metadata.get("file_path", ""))
        return file_path.replace("\\", "/").rsplit("/", 1)[-1].lower() != "overall.md"

    def granularity(self, metadata: Mapping[str, object]) -> tuple[str, float]:
        granularity = resolve_memory_granularity(metadata)
        return granularity, float(
            DEFAULT_GRANULARITY_SCORES.get(
                granularity,
                DEFAULT_GRANULARITY_SCORES["unknown"],
            )
        )


def resolve_memory_granularity(metadata: Mapping[str, object]) -> str:
    explicit = _normalize(
        metadata.get("memory_granularity") or metadata.get("granularity")
    )
    if explicit:
        return explicit
    semantic_type = _normalize(metadata.get("type"))
    if semantic_type:
        return semantic_type
    return "batch" if metadata.get("batch_id") is not None else "unknown"


def granularity_score(
    metadata: Mapping[str, object],
    scores: dict[str, float] | None = None,
) -> tuple[str, float]:
    granularity = resolve_memory_granularity(metadata)
    score_map = scores or DEFAULT_GRANULARITY_SCORES
    return granularity, float(score_map.get(granularity, score_map["unknown"]))


def _normalize(value: JsonValue | object) -> str:
    text = str(value or "").strip().lower()
    return _ALIASES.get(text, text) if text else ""
