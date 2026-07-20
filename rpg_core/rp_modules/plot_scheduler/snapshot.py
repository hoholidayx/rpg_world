"""Resolve immutable plot scheduling inputs before turn allocation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from rpg_core.rp_modules.constants import RP_MODULE_PLOT_SCHEDULER_NAME
from rpg_core.rp_modules.plot_scheduler.models import PlotScheduleSnapshot
from rpg_data import plot_models as data_models

if TYPE_CHECKING:
    from rpg_core.rp_modules.models import RPModuleSelectionSnapshot


class PlotScheduleSnapshotDataPort(Protocol):
    def get_session_state(
        self,
        session_id: str,
    ) -> tuple[
        data_models.StoryPlotSchedule,
        data_models.SessionPlotOverrides,
        list[data_models.SessionPlotScheduleDecision],
    ]: ...


class PlotScheduleSnapshotResolver:
    def __init__(self, data: PlotScheduleSnapshotDataPort) -> None:
        self._data = data

    def resolve(
        self,
        session_id: str,
        rp_modules: "RPModuleSelectionSnapshot",
    ) -> PlotScheduleSnapshot:
        selected = rp_modules.get(RP_MODULE_PLOT_SCHEDULER_NAME)
        if selected is None or not selected.effective_enabled:
            return PlotScheduleSnapshot.disabled(session_id, rp_modules.story_id)
        story, overrides, decisions = self._data.get_session_state(session_id)
        return PlotScheduleSnapshot(
            session_id=session_id,
            story_id=story.story_id,
            enabled=True,
            story=story,
            overrides=overrides,
            decisions=tuple(decisions),
            judge_history_turns=int(selected.effective_config["judge_history_turns"]),
            soft_retry_intervening_turns=int(
                selected.effective_config["soft_retry_intervening_turns"]
            ),
        )
