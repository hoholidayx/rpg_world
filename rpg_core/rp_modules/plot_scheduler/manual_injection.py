"""Turn-local state and atomic persistence for manual Plot injections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rpg_data import models as data_models


@dataclass
class PlotPendingInjectionTurnState:
    """Copy-on-write view of one persisted pending injection."""

    base: data_models.SessionPlotPendingInjection | None = None
    desired: data_models.PendingPlotInjectionWrite | None = None
    dirty: bool = False
    consume_base: bool = False

    def mark(self, values: data_models.PendingPlotInjectionWrite) -> None:
        self.desired = values
        self.dirty = True

    def clear(self) -> None:
        self.desired = None
        self.dirty = True

    def consume(self) -> None:
        if self.base is not None:
            self.consume_base = True

    @property
    def effective(self) -> (
        data_models.SessionPlotPendingInjection
        | data_models.PendingPlotInjectionWrite
        | None
    ):
        if self.dirty:
            return self.desired
        if self.consume_base:
            return None
        return self.base


class PlotPendingInjectionDataPort(Protocol):
    def replace_pending_injection(
        self,
        session_id: str,
        *,
        expected_version: int | None,
        values: data_models.PendingPlotInjectionWrite,
    ) -> data_models.SessionPlotPendingInjection: ...

    def clear_pending_injection(
        self,
        session_id: str,
        *,
        expected_version: int | None = None,
    ) -> int: ...


class PlotPendingInjectionCommitService:
    """Commit one turn's consume/replace/clear transition using CAS."""

    def __init__(self, data: PlotPendingInjectionDataPort) -> None:
        self._data = data

    def commit(
        self,
        session_id: str,
        state: PlotPendingInjectionTurnState,
    ) -> None:
        base = state.base
        if state.dirty:
            desired = state.desired
            if desired is None:
                if base is not None:
                    self._data.clear_pending_injection(
                        session_id,
                        expected_version=base.version,
                    )
                return
            self._data.replace_pending_injection(
                session_id,
                expected_version=base.version if base is not None else None,
                values=desired,
            )
            return

        if state.consume_base and base is not None:
            self._data.clear_pending_injection(
                session_id,
                expected_version=base.version,
            )


__all__ = [
    "PlotPendingInjectionCommitService",
    "PlotPendingInjectionDataPort",
    "PlotPendingInjectionTurnState",
]
