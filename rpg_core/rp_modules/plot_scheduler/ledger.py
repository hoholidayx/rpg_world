"""Plot decision-ledger policy owned by the Plot Scheduler domain."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from commons.scene_time import SceneTime
from rpg_data import models as data_models
from rpg_data.services.plot_scheduling import (
    PlotScheduleDataIntegrityError,
    PlotSchedulingDataService,
)

PLOT_DECISIONS_PER_TURN_MAX = len(data_models.PLOT_SOURCE_KINDS)


@dataclass(frozen=True)
class PlotScheduleDerivationCopyPolicy:
    copy_overrides: bool
    decision_statuses: frozenset[str]


PLOT_DERIVATION_COPY_POLICY = PlotScheduleDerivationCopyPolicy(
    copy_overrides=True,
    decision_statuses=frozenset((data_models.PLOT_DECISION_TRIGGERED,)),
)


class PlotScheduleLedgerConflictError(RuntimeError):
    """A validated decision batch conflicts with the persisted ledger."""


class PlotScheduleLedgerService:
    """Validate turn-local decisions before appending them to the SQL ledger."""

    def __init__(self, data: PlotSchedulingDataService) -> None:
        self._data = data

    def record(
        self,
        session_id: str,
        turn_id: int,
        decisions: Iterable[data_models.StagedPlotScheduleDecision],
    ) -> list[data_models.SessionPlotScheduleDecision]:
        staged = validate_plot_decision_batch(turn_id, decisions)
        try:
            return self._data.append_decisions(session_id, turn_id, staged)
        except PlotScheduleDataIntegrityError as exc:
            raise PlotScheduleLedgerConflictError(
                "plot schedule decision batch conflicts with the persisted ledger"
            ) from exc


def validate_plot_decision_batch(
    turn_id: int,
    decisions: Iterable[data_models.StagedPlotScheduleDecision],
) -> tuple[data_models.StagedPlotScheduleDecision, ...]:
    _positive(turn_id, "turn_id")
    staged = tuple(decisions)
    if len(staged) > PLOT_DECISIONS_PER_TURN_MAX:
        raise ValueError(
            "plot schedule decisions exceed the number of supported scheduling lanes"
        )
    source_kinds: set[str] = set()
    for decision in staged:
        if not isinstance(decision, data_models.StagedPlotScheduleDecision):
            raise TypeError("plot schedule decisions must use the typed staged contract")
        if decision.source_kind not in data_models.PLOT_SOURCE_KINDS:
            raise ValueError(f"unsupported plot source kind: {decision.source_kind}")
        if decision.source_kind in source_kinds:
            raise ValueError("only one plot schedule decision is allowed per source kind")
        source_kinds.add(decision.source_kind)
        if decision.decision_status not in data_models.PLOT_DECISION_STATUSES:
            raise ValueError(
                f"unsupported plot decision status: {decision.decision_status}"
            )
        if decision.dispatch_mode not in data_models.PLOT_DISPATCH_MODES:
            raise ValueError(
                f"unsupported plot dispatch mode: {decision.dispatch_mode}"
            )
        _positive(decision.source_id, "source_id")
        _positive(decision.event_id, "event_id")
        _positive(decision.container_id, "container_id")
        if not isinstance(decision.scene_time, SceneTime):
            raise ValueError("plot decision scene_time must be a SceneTime")
        if not isinstance(decision.event_snapshot, Mapping):
            raise ValueError("plot decision event_snapshot must be a mapping")
    return staged


def _positive(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


__all__ = [
    "PLOT_DECISIONS_PER_TURN_MAX",
    "PLOT_DERIVATION_COPY_POLICY",
    "PlotScheduleDerivationCopyPolicy",
    "PlotScheduleLedgerConflictError",
    "PlotScheduleLedgerService",
    "validate_plot_decision_batch",
]
