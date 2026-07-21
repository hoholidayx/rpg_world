"""Narrative Outcome ledger policy for committed Agent turns."""

from __future__ import annotations

from typing import Protocol

from rpg_core.rp_modules.narrative_outcome.models import (
    NARRATIVE_OUTCOME_DEFINITION_BY_CODE,
    StagedNarrativeOutcome,
)
from rpg_core.rp_modules.narrative_outcome.tools import NarrativeOutcomeSampler
from rpg_data.errors import DataIntegrityError
from rpg_data.model.narrative_outcome import (
    NARRATIVE_OUTCOME_SOURCES,
    NarrativeOutcomeCreate,
    NarrativeOutcomeRecord,
)


class NarrativeOutcomeLedgerDataPort(Protocol):
    def append(self, values: NarrativeOutcomeCreate) -> NarrativeOutcomeRecord: ...


class NarrativeOutcomeLedgerConflictError(RuntimeError):
    """A validated outcome conflicted with the persisted turn ledger."""


class NarrativeOutcomeLedgerService:
    """Validate staged Outcome semantics before appending one ledger row."""

    def __init__(self, data: NarrativeOutcomeLedgerDataPort) -> None:
        self._data = data

    def record(
        self,
        session_id: str,
        turn_id: int,
        staged: StagedNarrativeOutcome,
    ) -> NarrativeOutcomeRecord:
        normalized_turn_id = int(turn_id)
        if normalized_turn_id <= 0:
            raise ValueError("turn_id must be positive")
        definition = NARRATIVE_OUTCOME_DEFINITION_BY_CODE.get(staged.outcome_code)
        if definition is None:
            raise ValueError(
                f"invalid narrative outcome code: {staged.outcome_code}"
            )
        if isinstance(staged.sample_value, bool) or not isinstance(
            staged.sample_value,
            int,
        ):
            raise ValueError("sample_value must be an integer")
        sampled = NarrativeOutcomeSampler.definition_for_sample(
            staged.sample_value,
            staged.effective_weights,
        )
        if sampled.code != definition.code:
            raise ValueError(
                "narrative outcome code does not match sample and effective weights"
            )
        if staged.effective_source not in NARRATIVE_OUTCOME_SOURCES:
            raise ValueError(
                f"invalid narrative outcome source: {staged.effective_source}"
            )
        try:
            return self._data.append(
                NarrativeOutcomeCreate(
                    session_id=str(session_id),
                    turn_id=normalized_turn_id,
                    outcome_code=definition.code,
                    reason=str(staged.reason).strip(),
                    actor=str(staged.actor).strip(),
                    sample_value=int(staged.sample_value),
                    effective_weights=staged.effective_weights,
                    effective_source=staged.effective_source,
                )
            )
        except DataIntegrityError as exc:
            raise NarrativeOutcomeLedgerConflictError(
                "Narrative Outcome conflicts with the persisted turn ledger"
            ) from exc


__all__ = [
    "NarrativeOutcomeLedgerConflictError",
    "NarrativeOutcomeLedgerDataPort",
    "NarrativeOutcomeLedgerService",
]
