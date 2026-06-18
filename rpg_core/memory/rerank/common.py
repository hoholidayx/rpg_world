"""Shared prompt and parsing helpers for memory rerankers."""

from __future__ import annotations

import json
from typing import Any

from rpg_world.rpg_core.constants import MEMORY_RERANK_INSTRUCTIONS, MEMORY_RERANK_SYSTEM_PROMPT
from rpg_world.rpg_core.memory.candidate import MemoryCandidate


def build_rerank_prompt(query: str, candidates: list[MemoryCandidate]) -> str:
    payload = [
        {"id": str(candidate.memory_id), "content": candidate.content}
        for candidate in candidates
    ]
    return (
        f"{MEMORY_RERANK_SYSTEM_PROMPT}\n"
        f"{MEMORY_RERANK_INSTRUCTIONS}\n\n"
        f"用户查询：\n{query}\n\n"
        "候选记忆：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def extract_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        choices = output.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                return str(first.get("text") or first.get("message", {}).get("content") or "")
    return str(output)


def parse_json_array(text: str) -> list[Any]:
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("no JSON array found")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, list):
        raise ValueError("rerank output is not an array")
    return parsed
