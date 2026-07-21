"""Typed storage contracts for the Narrative Outcome ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

NARRATIVE_OUTCOME_CODES = (
    "critical_success",
    "success",
    "success_with_cost",
    "setback",
    "critical_failure",
)
NARRATIVE_OUTCOME_SOURCE_CONFIG = "config"
NARRATIVE_OUTCOME_SOURCE_STORY = "story"
NARRATIVE_OUTCOME_SOURCE_SESSION = "session"
NARRATIVE_OUTCOME_SOURCES = frozenset({
    NARRATIVE_OUTCOME_SOURCE_CONFIG,
    NARRATIVE_OUTCOME_SOURCE_STORY,
    NARRATIVE_OUTCOME_SOURCE_SESSION,
})


@dataclass(frozen=True)
class NarrativeOutcomeWeights:
    """Persisted snapshot of the five effective outcome weights."""

    critical_success: int = 5
    success: int = 25
    success_with_cost: int = 40
    setback: int = 25
    critical_failure: int = 5

    def __post_init__(self) -> None:
        values = self.values()
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("narrative outcome weights must be integers")
        if any(value < 0 or value > 100 for value in values):
            raise ValueError("narrative outcome weights must be within [0, 100]")
        if sum(values) != 100:
            raise ValueError("narrative outcome weights must sum to 100")

    def values(self) -> tuple[int, int, int, int, int]:
        return (
            self.critical_success,
            self.success,
            self.success_with_cost,
            self.setback,
            self.critical_failure,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "critical_success": self.critical_success,
            "success": self.success,
            "success_with_cost": self.success_with_cost,
            "setback": self.setback,
            "critical_failure": self.critical_failure,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "NarrativeOutcomeWeights":
        expected = set(NARRATIVE_OUTCOME_CODES)
        keys = set(raw)
        if keys != expected:
            missing = sorted(expected - keys)
            unexpected = sorted(keys - expected)
            raise ValueError(
                "narrative outcome weights must contain exactly five codes; "
                f"missing={missing}, unexpected={unexpected}"
            )
        return cls(
            critical_success=_weight_int(raw.get("critical_success"), "critical_success"),
            success=_weight_int(raw.get("success"), "success"),
            success_with_cost=_weight_int(
                raw.get("success_with_cost"),
                "success_with_cost",
            ),
            setback=_weight_int(raw.get("setback"), "setback"),
            critical_failure=_weight_int(
                raw.get("critical_failure"),
                "critical_failure",
            ),
        )


@dataclass(frozen=True)
class NarrativeOutcomeCreate:
    """Caller-prepared values for one persisted turn outcome."""

    session_id: str
    turn_id: int
    outcome_code: str
    reason: str
    actor: str
    sample_value: int
    effective_weights: NarrativeOutcomeWeights
    effective_source: str


@dataclass(frozen=True)
class NarrativeOutcomeRecord:
    id: int
    session_id: str
    turn_id: int
    outcome_code: str
    reason: str
    actor: str
    sample_value: int
    effective_weights: NarrativeOutcomeWeights
    effective_source: str
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


def _weight_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"narrative outcome weight {name} must be an integer")
    return value


__all__ = [
    "NARRATIVE_OUTCOME_CODES",
    "NARRATIVE_OUTCOME_SOURCE_CONFIG",
    "NARRATIVE_OUTCOME_SOURCE_SESSION",
    "NARRATIVE_OUTCOME_SOURCE_STORY",
    "NARRATIVE_OUTCOME_SOURCES",
    "NarrativeOutcomeCreate",
    "NarrativeOutcomeRecord",
    "NarrativeOutcomeWeights",
]
