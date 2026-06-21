"""Structured query plan for memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    """Normalized query variants consumed by memory retrievers."""

    original_query: str
    normalized_query: str
    keyword_queries: tuple[str, ...]
    expanded_queries: tuple[str, ...]
    raw_md_terms: tuple[str, ...]
    query_type: str = "general"
    planner_source: str = "rule_based"



def make_empty_plan(query: str, planner_source: str = "rule_based") -> QueryPlan:
    return QueryPlan(
        original_query=query,
        normalized_query="",
        keyword_queries=(),
        expanded_queries=(),
        raw_md_terms=(),
        planner_source=planner_source,
    )
