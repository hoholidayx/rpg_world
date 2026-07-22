"""RP-specific prompt policy for the generic pointwise reranker."""

from __future__ import annotations

from memory_retrieval.candidate import MemoryCandidate
from memory_retrieval.rerank.common import build_pointwise_prompt


RP_MEMORY_RERANK_POINTWISE_INSTRUCTIONS = (
    "任务：判断候选记忆是否能回答用户查询。\n"
    "RP：传闻/推测/不确定≠事实，尝试≠成功，承诺/计划≠完成；查询正问该类型时可高相关。\n"
    "分数：0无关，30弱相关，60相关，80强相关，100精确命中。\n"
    "输出格式：<0-100整数>\\t<8字内原因>\n"
    "禁止输出其他内容。"
)


def build_rp_pointwise_prompt(
    query: str,
    candidate: MemoryCandidate,
    max_candidate_chars: int = 2400,
) -> str:
    """Preserve RP epistemic and outcome semantics in rerank scoring."""
    epistemic_status = str(candidate.metadata.get("epistemic_status", "") or "")
    memory_kind = str(candidate.metadata.get("memory_kind", "") or "")
    candidate_context = ""
    if memory_kind or epistemic_status:
        candidate_context = (
            f"类型：{memory_kind or '未知'}；认知：{epistemic_status or '未知'}\n"
        )
    return build_pointwise_prompt(
        query,
        candidate,
        max_candidate_chars,
        instructions=RP_MEMORY_RERANK_POINTWISE_INSTRUCTIONS,
        candidate_context=candidate_context,
    )
