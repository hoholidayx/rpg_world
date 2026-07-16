"""Strict JSON decoding shared by Media LLM capabilities."""

from __future__ import annotations

import json
from collections.abc import Mapping


def parse_json_object(content: str, *, label: str) -> dict[str, object]:
    text = str(content).strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be a JSON object") from exc
    if not isinstance(parsed, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in parsed.items()}
