"""Shared candidate model for memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryCandidate:
    """A memory chunk with scores from multiple retrieval signals."""

    memory_id: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    vector_score: float = 0.0
    keyword_score: float = 0.0
    raw_md_score: float = 0.0
    exact_score: float = 0.0
    fuzzy_score: float = 0.0
    expanded_score: float = 0.0
    granularity_score: float = 0.0
    recency_score: float = 0.0
    hybrid_score: float = 0.0
    rerank_score: float = 0.0
    debug: dict[str, Any] = field(default_factory=dict)

    @property
    def final_score(self) -> float:
        """Return the score used for final ordering."""
        return self.rerank_score or self.hybrid_score
