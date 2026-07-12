"""Agent turn transaction orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.context.rpg_context import Role
from rpg_core.scene import SceneTracker
from rpg_core.agent.transaction.commit_plan import TurnCommitPlan
from rpg_core.agent.transaction.message_scratch import MessageScratch
from rpg_core.agent.transaction.status_scratch import (
    ScratchStatusManager,
    StatusDocumentChange,
    StatusDocumentScratch,
)
from rpg_core.agent.transaction.scratch import TurnScratch

if TYPE_CHECKING:
    from rpg_core.agent.agent_types import TurnStats
    from rpg_core.context.rpg_context import Message
    from rpg_core.session import SessionManager
    from rpg_core.status.manager import StatusManager

_TAG = "[AgentTurnTransaction]"


class AgentTurnTransaction:
    """Coordinates one send/send_stream turn scratch and commit."""

    def __init__(
        self,
        *,
        session: "SessionManager",
        status_mgr: "StatusManager | None",
        scene_tracker: SceneTracker | None,
    ) -> None:
        self._session = session
        self._status_mgr = status_mgr
        self._real_scene_tracker = scene_tracker
        self._turn_id: int | None = None
        self._scratch: TurnScratch | None = None
        self._committed = False

    @property
    def scratch(self) -> TurnScratch:
        if self._scratch is None:
            raise RuntimeError("Agent turn transaction has not begun")
        return self._scratch

    def begin(self, turn_stats: "TurnStats", *, mode: str = "ic") -> TurnScratch:
        turn_id: int | None = None
        try:
            turn_id = self._session.begin_turn()
            self._turn_id = turn_id
            message_scratch = MessageScratch(
                turn_id=turn_id,
                base_history=self._session.history,
                mode=mode,
            )
            status_scratch = StatusDocumentScratch(self._status_mgr)
            scratch_status_mgr = ScratchStatusManager(self._status_mgr, status_scratch)
            scratch_scene_tracker = self._build_scratch_scene_tracker(scratch_status_mgr)
            self._scratch = TurnScratch(
                message_scratch=message_scratch,
                status_scratch=status_scratch,
                status_manager=scratch_status_mgr,
                scene_tracker=scratch_scene_tracker,
                turn_stats=turn_stats,
            )
        except Exception as exc:
            if turn_id is not None:
                self._session.end_turn(turn_id)
            self._turn_id = None
            self._scratch = None
            logger.opt(exception=exc).error(_TAG + " begin failed; cleared active turn")
            raise
        return self._scratch

    def stage_user_message(self, content: str) -> "Message":
        return self.scratch.stage_message(Role.USER, content)

    def stage_assistant_message(self, content: str) -> "Message":
        return self.scratch.stage_message(Role.ASSISTANT, content)

    def build_commit_plan(self) -> TurnCommitPlan:
        return TurnCommitPlan(
            session=self._session,
            status_mgr=self._status_mgr,
            message_scratch=self.scratch.message_scratch,
            status_scratch=self.scratch.status_scratch,
            narrative_outcome=self.scratch.narrative_outcome,
        )

    def commit(self) -> list[StatusDocumentChange]:
        changes = self.build_commit_plan().commit()
        self._committed = True
        logger.debug(
            _TAG + " committed turn: turn_id={} messages={} status_documents={} narrative_outcome={}",
            self._turn_id,
            len(self.scratch.staged_messages),
            len(changes),
            self.scratch.narrative_outcome.outcome_code
            if self.scratch.narrative_outcome is not None
            else None,
        )
        return changes

    def discard(self) -> None:
        self._scratch = None

    def close(self) -> None:
        turn_id = self._turn_id
        self._session.end_turn(turn_id)
        self._turn_id = None
        if not self._committed:
            self.discard()

    def _build_scratch_scene_tracker(self, status_mgr: ScratchStatusManager) -> SceneTracker | None:
        if self._real_scene_tracker is None:
            return None
        tracker = SceneTracker()
        tracker.set_time_state(self._real_scene_tracker.get_time_state())
        tracker.bind_status_manager(status_mgr)
        tracker.load_from_status_table()
        return tracker
