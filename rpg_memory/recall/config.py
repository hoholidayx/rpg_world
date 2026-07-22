"""Structural configuration contract for RP recall orchestration."""

from __future__ import annotations

from typing import Protocol


class MemoryRecallConfig(Protocol):
    """Configuration fields consumed by :class:`MemoryRecallManager`.

    The application-owned ``rpg_core.settings.MemorySettings`` satisfies this
    contract structurally, so the RP memory package does not depend on the
    application's settings implementation.
    """

    enabled: bool
    top_k: int
    hybrid_enabled: bool
    vector_k: int
    keyword_tokenizer: str
    keyword_k: int
    hybrid_vector_weight: float
    hybrid_keyword_weight: float
    hybrid_raw_md_weight: float
    hybrid_exact_weight: float
    hybrid_expanded_weight: float
    hybrid_recency_weight: float
    hybrid_granularity_weight: float
    raw_md_mode: str
    raw_md_min_results: int
    rerank_candidate_k: int
    rerank_score_weight: float
    rerank_enabled: bool
    query_planner_enabled: bool
    jieba_dict: str
    chunk_size: int
    chunk_overlap: int
