"""Turn-local state and atomic persistence for Scene-driven Plot opportunities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rpg_data import models as data_models


@dataclass
class PlotSceneOpportunityTurnState:
    """Copy-on-write state for one delayed automatic scheduling opportunity."""

    base: data_models.SessionPlotSceneOpportunity | None = None
    consume_base: bool = False
    desired_source_turn_id: int | None = None
    dirty: bool = False

    @property
    def available(self) -> bool:
        return self.base is not None and not self.consume_base

    def consume(self) -> None:
        if self.base is not None:
            self.consume_base = True

    def finalize(self, *, source_turn_id: int, scene_changed: bool) -> None:
        """Resolve durable state after all turn-local Scene writes finish."""
        if scene_changed:
            self.desired_source_turn_id = int(source_turn_id)
            self.dirty = True
            return
        if self.consume_base:
            self.desired_source_turn_id = None
            self.dirty = True


class PlotSceneOpportunityDataPort(Protocol):
    def replace_scene_opportunity(
        self,
        session_id: str,
        *,
        expected_version: int | None,
        source_turn_id: int,
    ) -> data_models.SessionPlotSceneOpportunity: ...

    def clear_scene_opportunity(
        self,
        session_id: str,
        *,
        expected_version: int | None = None,
    ) -> int: ...


class PlotSceneOpportunityCommitService:
    """Commit one turn's consume-or-replace transition using CAS."""

    def __init__(self, data: PlotSceneOpportunityDataPort) -> None:
        self._data = data

    def commit(
        self,
        session_id: str,
        state: PlotSceneOpportunityTurnState,
    ) -> None:
        if not state.dirty:
            return
        base = state.base
        source_turn_id = state.desired_source_turn_id
        if source_turn_id is not None:
            self._data.replace_scene_opportunity(
                session_id,
                expected_version=base.version if base is not None else None,
                source_turn_id=source_turn_id,
            )
            return
        if base is not None:
            self._data.clear_scene_opportunity(
                session_id,
                expected_version=base.version,
            )


__all__ = [
    "PlotSceneOpportunityCommitService",
    "PlotSceneOpportunityDataPort",
    "PlotSceneOpportunityTurnState",
]
