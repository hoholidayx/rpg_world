"""Business-neutral input for contextual retrieval planning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalQuery:
    """Normalized context supplied to a query planner by an application adapter."""

    text: str
    expansions: tuple[str, ...] = ()
    keyword_context: tuple[str, ...] = ()
    prompt_context: str = ""
