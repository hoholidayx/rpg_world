"""Resolve immutable plot scheduling inputs before turn allocation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.rp_modules.constants import RP_MODULE_PLOT_SCHEDULER_NAME
from rpg_core.rp_modules.plot_scheduler.models import PlotScheduleSnapshot

if TYPE_CHECKING:
    from rpg_core.rp_modules.models import RPModuleSelectionSnapshot
    from rpg_data.services import DataServiceGateway


class PlotScheduleSnapshotResolver:
    def __init__(self, gateway: "DataServiceGateway | None" = None) -> None:
        self._gateway = gateway

    def resolve(
        self,
        session_id: str,
        rp_modules: "RPModuleSelectionSnapshot",
    ) -> PlotScheduleSnapshot:
        selected = rp_modules.get(RP_MODULE_PLOT_SCHEDULER_NAME)
        if selected is None or not selected.effective_enabled:
            return PlotScheduleSnapshot.disabled(session_id, rp_modules.story_id)
        gateway = self._get_gateway()
        story, overrides, decisions = gateway.plot_scheduling.get_session_state(
            session_id
        )
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

    def _get_gateway(self) -> "DataServiceGateway":
        if self._gateway is None:
            from rpg_data.services import get_data_service_gateway

            self._gateway = get_data_service_gateway()
        return self._gateway
