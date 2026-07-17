"""Normalization and command projections for the memory workflow."""

from __future__ import annotations

from rpg_core.agent.sub_agents.memory.models import MemoryAgentResult, MemoryPipelineError
from rpg_core.agent.telemetry import CallRecord


def normalize_story_detail(raw: object) -> dict[str, object]:
    if isinstance(raw, str):
        return {
            "text": raw,
            "memory_kind": "event",
            "epistemic_status": "confirmed",
            "salience": 0.5,
            "metadata": {},
        }
    if not isinstance(raw, dict):
        raise MemoryPipelineError("each story memory detail must be an object")
    text = " ".join(str(raw.get("text", "") or "").split())
    if not text:
        raise MemoryPipelineError("story memory detail text must not be empty")
    metadata: dict[str, object] = {}
    for key in ("entities", "story_time", "location"):
        value = raw.get(key)
        if value not in (None, "", []):
            metadata[key] = value
    return {
        "text": text,
        "memory_kind": str(raw.get("memory_kind", "event") or "event"),
        "epistemic_status": str(raw.get("epistemic_status", "confirmed") or "confirmed"),
        "salience": raw.get("salience", 0.5),
        "metadata": metadata,
    }


def build_call_stats(result: MemoryAgentResult) -> dict[str, float | str | int] | None:
    return build_call_stats_from_records(tuple(result.call_stats))


def build_call_stats_from_records(
    records: tuple[CallRecord, ...],
) -> dict[str, float | str | int] | None:
    if not records:
        return None
    record = records[0]
    return {
        "total_duration_ms": record.duration_ms,
        "model": record.model,
        "prompt_tokens": record.usage.prompt_tokens if record.usage else 0,
        "completion_tokens": record.usage.completion_tokens if record.usage else 0,
        "total_tokens": record.usage.total_tokens if record.usage else 0,
        "cached_tokens": record.usage.cached_tokens if record.usage else 0,
    }


def parse_int_arg(args: list[str], index: int) -> tuple[int | None, str | None]:
    if index >= len(args):
        return None, None
    try:
        return int(args[index]), None
    except ValueError:
        return None, args[index]


def format_store_items(
    items: list[dict],
    *,
    key: type = str,
    max_items: int | None = None,
    max_item_chars: int | None = None,
) -> str:
    if max_items is not None:
        items = items[-max_items:]
    if not items:
        return "(empty)"
    rendered: list[str] = []
    for item in items:
        value = str(key(item))
        if max_item_chars is not None:
            value = value[:max_item_chars]
        rendered.append(f"- {value}")
    return "\n".join(rendered)
