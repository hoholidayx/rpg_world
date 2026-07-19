"""Turn scratch state for agent transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rpg_core.context.models import Message, Role
from rpg_core.agent.turn.transaction.message_scratch import MessageScratch
from rpg_core.agent.turn.transaction.status_scratch import ScratchStatusManager, StatusDocumentScratch

if TYPE_CHECKING:
    from rpg_data.models import StagedPlotScheduleDecision
    from rpg_core.rp_modules.plot_scheduler.models import PlotScheduleInjection
    from rpg_core.agent.telemetry import TurnStats
    from rpg_core.rp_modules.narrative_outcome.models import StagedNarrativeOutcome
    from rpg_core.scene import SceneTracker
    from rpg_core.rp_modules.models import RPModuleSelectionSnapshot
    from rpg_core.rp_modules.narrative_outcome.models import NarrativeOutcomeSelection
    from rpg_core.rp_modules.runtime import RPModuleTurnRuntime


@dataclass
class TurnScratch:
    """Memory-only working state for one agent turn."""

    message_scratch: MessageScratch
    status_scratch: StatusDocumentScratch
    status_manager: ScratchStatusManager
    scene_tracker: "SceneTracker | None"
    turn_stats: "TurnStats"
    tool_records: list[object] = field(default_factory=list)
    narrative_outcome_selection: "NarrativeOutcomeSelection | None" = None
    narrative_outcome: "StagedNarrativeOutcome | None" = None
    rp_module_snapshot: "RPModuleSelectionSnapshot | None" = None
    rp_module_runtime: "RPModuleTurnRuntime | None" = None
    plot_schedule_decisions: list["StagedPlotScheduleDecision"] = field(default_factory=list)
    plot_schedule_injections: list["PlotScheduleInjection"] = field(default_factory=list)

    @property
    def turn_id(self) -> int:
        return self.message_scratch.turn_id

    @property
    def base_history(self) -> list[Message]:
        return self.message_scratch.base_history

    @property
    def staged_messages(self) -> list[Message]:
        return self.message_scratch.staged_messages

    def stage_message(self, role: Role | str, content: str) -> Message:
        return self.message_scratch.stage(role, content)
