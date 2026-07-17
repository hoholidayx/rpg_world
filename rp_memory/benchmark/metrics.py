"""Deterministic evidence-retrieval metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RecallMetrics:
    cases: int
    evaluated_cases: int
    answerable_cases: int
    no_answer_cases: int
    unscored_cases: int
    hit_at_1: float
    recall_at_k: float
    mrr: float
    ndcg: float
    evidence_coverage: float
    no_answer_accuracy: float | None


@dataclass(frozen=True)
class RPRecallMetrics:
    cases: int
    evaluated_cases: int
    answerable_cases: int
    no_answer_cases: int
    unscored_cases: int
    hit_at_1: float
    recall_at_k: float
    mrr: float
    ndcg: float
    evidence_coverage: float
    no_answer_accuracy: float | None
    forbidden_cases: int
    forbidden_at_1_rate: float
    forbidden_hit_rate: float
    forbidden_before_gold_rate: float


def evaluate_rankings(
    cases: list[tuple[list[str], list[str]]],
    *,
    top_k: int,
    unscored_cases: int = 0,
) -> RecallMetrics:
    unscored = max(0, int(unscored_cases))
    if not cases:
        return RecallMetrics(
            unscored, 0, 0, 0, unscored, 0.0, 0.0, 0.0, 0.0, 0.0, None
        )
    top_one_hits = hits = reciprocal = ndcg_total = coverage = 0.0
    no_answer_total = no_answer_correct = 0
    for gold_values, ranked_values in cases:
        gold = set(gold_values)
        ranked = ranked_values[: max(1, int(top_k))]
        if not gold:
            no_answer_total += 1
            if not ranked:
                no_answer_correct += 1
            continue
        relevant_ranks = [index for index, value in enumerate(ranked, start=1) if value in gold]
        if relevant_ranks:
            hits += 1.0
            reciprocal += 1.0 / relevant_ranks[0]
            if relevant_ranks[0] == 1:
                top_one_hits += 1.0
        matched = len(gold.intersection(ranked))
        coverage += matched / len(gold)
        dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
        ideal = sum(
            1.0 / math.log2(rank + 1)
            for rank in range(1, min(len(gold), len(ranked)) + 1)
        )
        ndcg_total += dcg / ideal if ideal else 0.0
    answerable = sum(1 for gold, _ in cases if gold)
    return RecallMetrics(
        cases=len(cases) + unscored,
        evaluated_cases=len(cases),
        answerable_cases=answerable,
        no_answer_cases=no_answer_total,
        unscored_cases=unscored,
        hit_at_1=top_one_hits / answerable if answerable else 0.0,
        recall_at_k=hits / answerable if answerable else 0.0,
        mrr=reciprocal / answerable if answerable else 0.0,
        ndcg=ndcg_total / answerable if answerable else 0.0,
        evidence_coverage=coverage / answerable if answerable else 0.0,
        no_answer_accuracy=(
            no_answer_correct / no_answer_total if no_answer_total else None
        ),
    )


def evaluate_rp_rankings(
    cases: list[tuple[list[str], list[str], list[str]]],
    *,
    top_k: int,
) -> RPRecallMetrics:
    base = evaluate_rankings(
        [(gold, ranked) for gold, _, ranked in cases],
        top_k=top_k,
    )
    constrained = [
        (set(gold), set(forbidden), ranked[:top_k])
        for gold, forbidden, ranked in cases
        if forbidden
    ]
    top_one_violations = sum(
        1 for _, forbidden, ranked in constrained if ranked and ranked[0] in forbidden
    )
    violations = sum(1 for _, forbidden, ranked in constrained if forbidden.intersection(ranked))
    ordering_violations = 0
    for gold, forbidden, ranked in constrained:
        first_gold = min(
            (index for index, value in enumerate(ranked) if value in gold),
            default=len(ranked) + 1,
        )
        first_forbidden = min(
            (index for index, value in enumerate(ranked) if value in forbidden),
            default=len(ranked) + 1,
        )
        if first_forbidden < first_gold:
            ordering_violations += 1
    return RPRecallMetrics(
        **base.__dict__,
        forbidden_cases=len(constrained),
        forbidden_at_1_rate=(
            top_one_violations / len(constrained) if constrained else 0.0
        ),
        forbidden_hit_rate=violations / len(constrained) if constrained else 0.0,
        forbidden_before_gold_rate=(
            ordering_violations / len(constrained) if constrained else 0.0
        ),
    )
