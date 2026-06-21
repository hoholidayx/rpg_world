"""Shared prompt, parsing, and fusion helpers for memory rerankers."""

from __future__ import annotations

from typing import Any

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.retrieval.scoring import normalize_values


MEMORY_RERANK_SYSTEM_PROMPT = "你是一个本地记忆检索重排器。"
MEMORY_RERANK_POINTWISE_INSTRUCTIONS = (
    "请只根据用户查询和单条候选记忆判断相关性。\n"
    "只根据候选内容本身打分，不要编造。\n"
    "评分：\n"
    "0 = 完全无关\n"
    "30 = 弱相关\n"
    "60 = 有一定相关\n"
    "80 = 强相关\n"
    "100 = 精确命中\n"
    "只输出一行，格式严格为：<0-100整数分数>\\t<简短原因>\n"
    "不要输出 JSON，不要代码块，不要解释。"
)


def build_pointwise_prompt(query: str, candidate: MemoryCandidate) -> str:
    return (
        f"{MEMORY_RERANK_SYSTEM_PROMPT}\n"
        f"{MEMORY_RERANK_POINTWISE_INSTRUCTIONS}\n\n"
        f"用户查询：{query}\n\n"
        f"候选记忆：{candidate.content}"
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


def parse_pointwise_output(text: str) -> tuple[float, str]:
    cleaned = short_preview(text, limit=4000)
    if not cleaned:
        raise ValueError("empty rerank output")
    first_line = cleaned.splitlines()[0].strip()
    if not first_line:
        raise ValueError("empty rerank output")
    parts = first_line.split("\t")
    if len(parts) == 1:
        parts = [part.strip() for part in first_line.split("|") if part.strip()]
    if len(parts) == 1:
        parts = [part.strip() for part in first_line.split(",") if part.strip()]
    score_text = parts[0]
    reason = parts[1] if len(parts) >= 2 else ""
    try:
        score = float(score_text)
    except Exception:
        import re

        match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", first_line)
        if not match:
            raise ValueError(f"no numeric score found: {first_line!r}")
        score = float(match.group(1))
        if len(parts) >= 2:
            reason = parts[-1]
    return score, reason


def short_preview(text: str, limit: int = 800) -> str:
    return " ".join((text or "").split())[:limit]


def blend_pointwise_scores(
    candidates: list[MemoryCandidate],
    pointwise_scores: dict[int, float],
    reasons: dict[int, str],
    rerank_weight: float,
    debug_score_key: str,
    debug_reason_key: str,
) -> list[MemoryCandidate]:
    normalized = {
        memory_id: max(0.0, min(1.0, score / 100.0))
        for memory_id, score in pointwise_scores.items()
    }
    hybrid_norm = normalize_values(candidates, lambda item: item.hybrid_score)
    for candidate in candidates:
        score_norm = normalized.get(candidate.memory_id, 0.0)
        candidate.rerank_score = (
            rerank_weight * score_norm
            + (1.0 - rerank_weight) * hybrid_norm[candidate.memory_id]
        )
        candidate.debug[debug_score_key] = score_norm
        reason = reasons.get(candidate.memory_id, "")
        if reason:
            candidate.debug[debug_reason_key] = reason
    return sorted(candidates, key=lambda item: item.final_score, reverse=True)
