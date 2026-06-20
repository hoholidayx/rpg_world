"""String boosts and hybrid score fusion for retrieval."""

from __future__ import annotations

from collections.abc import Callable
from difflib import SequenceMatcher

from rpg_world.rpg_core.memory.candidate import MemoryCandidate


def exact_and_fuzzy_scores(query: str, content: str) -> tuple[float, float]:
    """Return ``(exact_score, fuzzy_score)`` normalized to 0..1."""
    query = " ".join((query or "").split())
    content = content or ""
    if not query or not content:
        return 0.0, 0.0
    if query in content:
        return 1.0, 1.0

    fuzzy = _partial_ratio(query, content)
    return 0.0, fuzzy


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


def apply_hybrid_scores(
    candidates: list[MemoryCandidate],
    vector_weight: float = 0.60,
    bigram_weight: float = 0.25,
    exact_weight: float = 0.10,
    recency_weight: float = 0.05,
) -> None:
    """Apply weighted hybrid scoring formula in-place.

    Weights default to the historical hardcoded values and can be
    overridden via ``memory.hybrid_*_weight`` in settings.yaml.
    """
    vector_norm = normalize_values(candidates, lambda item: item.vector_score)
    bigram_norm = normalize_values(candidates, lambda item: item.bigram_score)
    recency_norm = normalize_values(candidates, lambda item: item.recency_score)

    for candidate in candidates:
        exact_or_fuzzy = max(candidate.exact_score, candidate.fuzzy_score)
        candidate.debug.update(
            {
                "vector_score_norm": vector_norm[candidate.memory_id],
                "bigram_score_norm": bigram_norm[candidate.memory_id],
                "recency_score_norm": recency_norm[candidate.memory_id],
                "exact_or_fuzzy_score": exact_or_fuzzy,
            }
        )
        candidate.hybrid_score = (
            vector_weight * vector_norm[candidate.memory_id]
            + bigram_weight * bigram_norm[candidate.memory_id]
            + exact_weight * exact_or_fuzzy
            + recency_weight * recency_norm[candidate.memory_id]
        )


def _partial_ratio(query: str, content: str) -> float:
    if len(content) <= len(query):
        return SequenceMatcher(None, query, content).ratio()

    best = SequenceMatcher(None, query, content).ratio()
    window = len(query)
    step = max(1, window // 2)
    for start in range(0, len(content) - window + 1, step):
        part = content[start : start + window]
        best = max(best, SequenceMatcher(None, query, part).ratio())
        if best >= 1.0:
            break
    return max(0.0, min(1.0, best))
