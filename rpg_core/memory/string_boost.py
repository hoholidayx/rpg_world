"""Lightweight exact and fuzzy string boosts for memory retrieval."""

from __future__ import annotations

from difflib import SequenceMatcher


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
