"""Score normalization and fusion for hybrid memory retrieval."""

from __future__ import annotations

from collections.abc import Callable

from rpg_world.rpg_core.memory.candidate import MemoryCandidate


def normalize_values(
    candidates: list[MemoryCandidate],
    getter: Callable[[MemoryCandidate], float],
) -> dict[int, float]:
    """Min-max normalize candidate values by memory id."""
    values = {candidate.memory_id: float(getter(candidate) or 0.0) for candidate in candidates}
    positives = [value for value in values.values() if value > 0.0]
    if not positives:
        return {memory_id: 0.0 for memory_id in values}

    low = min(positives)
    high = max(positives)
    if high == low:
        return {
            memory_id: 1.0 if value > 0.0 else 0.0
            for memory_id, value in values.items()
        }
    return {
        memory_id: ((value - low) / (high - low)) if value > 0.0 else 0.0
        for memory_id, value in values.items()
    }


def apply_hybrid_scores(candidates: list[MemoryCandidate]) -> None:
    """Apply the default weighted hybrid scoring formula in-place."""
    vector_norm = normalize_values(candidates, lambda item: item.vector_score)
    keyword_norm = normalize_values(candidates, lambda item: item.keyword_score)
    recency_norm = normalize_values(candidates, lambda item: item.recency_score)

    for candidate in candidates:
        exact_or_fuzzy = max(candidate.exact_score, candidate.fuzzy_score)
        candidate.debug.update(
            {
                "vector_score_norm": vector_norm[candidate.memory_id],
                "keyword_score_norm": keyword_norm[candidate.memory_id],
                "recency_score_norm": recency_norm[candidate.memory_id],
                "exact_or_fuzzy_score": exact_or_fuzzy,
            }
        )
        candidate.hybrid_score = (
            0.60 * vector_norm[candidate.memory_id]
            + 0.25 * keyword_norm[candidate.memory_id]
            + 0.10 * exact_or_fuzzy
            + 0.05 * recency_norm[candidate.memory_id]
        )
