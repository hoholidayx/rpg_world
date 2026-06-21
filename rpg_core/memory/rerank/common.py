"""Shared prompt, parsing, and fusion helpers for memory rerankers."""

from __future__ import annotations

from typing import Any

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.retrieval.scoring import normalize_values


MEMORY_RERANK_SYSTEM_PROMPT = "你是记忆检索重排器。只输出评分行。"
MEMORY_RERANK_POINTWISE_INSTRUCTIONS = (
    "任务：判断候选记忆是否能回答用户查询。\n"
    "分数：0无关，30弱相关，60相关，80强相关，100精确命中。\n"
    "输出格式：<0-100整数>\\t<8字内原因>\n"
    "禁止输出其他内容。"
)


def build_pointwise_prompt(query: str, candidate: MemoryCandidate, *, max_candidate_chars: int = 2400) -> str:
    content = _truncate_candidate_content(candidate.content, max_candidate_chars)
    return (
        f"{MEMORY_RERANK_POINTWISE_INSTRUCTIONS}\n\n"
        f"查询：{query}\n"
        f"候选：{content}\n"
        "评分："
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
    cleaned = (text or "").strip()[:4000]
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


def _truncate_candidate_content(content: str, max_chars: int) -> str:
    if max_chars <= 0 or len(content) <= max_chars:
        return content
    return f"{content[:max_chars]}\n...[候选记忆已截断，仅用于重排]"


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
