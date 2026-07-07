"""Turn scratch state for agent transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rpg_core.context.rpg_context import Message, Role
from rpg_core.agent.transaction.message_scratch import MessageScratch
from rpg_core.agent.transaction.status_scratch import ScratchStatusManager, StatusDocumentScratch

if TYPE_CHECKING:
    from rpg_core.agent.agent_types import TurnStats
    from rpg_core.scene import SceneTracker


@dataclass
class TurnScratch:
    """Memory-only working state for one agent turn."""

    message_scratch: MessageScratch
    status_scratch: StatusDocumentScratch
    status_manager: ScratchStatusManager
    scene_tracker: "SceneTracker | None"
    turn_stats: "TurnStats"
    tool_records: list[object] = field(default_factory=list)

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

    def history_for_context(self) -> list[Message]:
        return self.message_scratch.history_for_context()
