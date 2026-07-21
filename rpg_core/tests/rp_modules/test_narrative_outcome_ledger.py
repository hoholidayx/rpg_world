from __future__ import annotations

from dataclasses import replace

import pytest

from rpg_core.rp_modules.narrative_outcome import (
    NarrativeOutcomeLedgerConflictError,
    NarrativeOutcomeLedgerService,
    StagedNarrativeOutcome,
)
from rpg_data import models
from rpg_data.errors import DataIntegrityError


class _OutcomeData:
    def __init__(self, *, conflict: bool = False) -> None:
        self.conflict = conflict
        self.appended: list[models.NarrativeOutcomeCreate] = []

    def append(
        self,
        values: models.NarrativeOutcomeCreate,
    ) -> models.NarrativeOutcomeRecord:
        if self.conflict:
            raise DataIntegrityError("duplicate turn")
        self.appended.append(values)
        return models.NarrativeOutcomeRecord(
            id=len(self.appended),
            session_id=values.session_id,
            turn_id=values.turn_id,
            outcome_code=values.outcome_code,
            reason=values.reason,
            actor=values.actor,
            sample_value=values.sample_value,
            effective_weights=values.effective_weights,
            effective_source=values.effective_source,
        )


def _staged() -> StagedNarrativeOutcome:
    return StagedNarrativeOutcome(
        outcome_code="success_with_cost",
        label="成功但有代价",
        narrative_guidance="完整达成并承担代价",
        reason="  穿过摇晃的吊桥  ",
        actor="  Alice  ",
        sample_value=50,
        effective_weights=models.NarrativeOutcomeWeights(),
        effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
    )


def test_ledger_validates_and_appends_caller_staged_outcome() -> None:
    data = _OutcomeData()

    created = NarrativeOutcomeLedgerService(data).record("s1", 7, _staged())

    assert created.outcome_code == "success_with_cost"
    assert data.appended == [
        models.NarrativeOutcomeCreate(
            session_id="s1",
            turn_id=7,
            outcome_code="success_with_cost",
            reason="穿过摇晃的吊桥",
            actor="Alice",
            sample_value=50,
            effective_weights=models.NarrativeOutcomeWeights(),
            effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
        )
    ]


@pytest.mark.parametrize(
    "staged",
    [
        replace(_staged(), outcome_code="unknown"),
        replace(_staged(), outcome_code="success"),
        replace(_staged(), sample_value=0),
        replace(_staged(), sample_value=True),
        replace(_staged(), effective_source="unknown"),
    ],
)
def test_ledger_rejects_invalid_outcome_policy(
    staged: StagedNarrativeOutcome,
) -> None:
    with pytest.raises(ValueError):
        NarrativeOutcomeLedgerService(_OutcomeData()).record("s1", 7, staged)


def test_ledger_rejects_non_positive_turn() -> None:
    with pytest.raises(ValueError, match="turn_id must be positive"):
        NarrativeOutcomeLedgerService(_OutcomeData()).record("s1", 0, _staged())


def test_ledger_maps_data_integrity_to_domain_conflict() -> None:
    with pytest.raises(NarrativeOutcomeLedgerConflictError):
        NarrativeOutcomeLedgerService(_OutcomeData(conflict=True)).record(
            "s1",
            7,
            _staged(),
        )
