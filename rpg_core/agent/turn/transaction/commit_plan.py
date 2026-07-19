"""Commit plan for one successful agent turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.turn.transaction.message_scratch import MessageScratch
from rpg_core.agent.turn.transaction.status_scratch import StatusDocumentChange, StatusDocumentScratch
from rpg_core.session import InvalidTurnMetadataError

if TYPE_CHECKING:
    from rpg_data.models import StagedPlotScheduleDecision
    from rpg_core.rp_modules.narrative_outcome.models import StagedNarrativeOutcome
    from rpg_core.session import SessionManager
    from rpg_core.status.manager import StatusManager

_TAG = "[AgentTurnTransaction]"


@dataclass
class TurnCommitPlan:
    """Durable writes produced by a successful agent turn."""

    session: "SessionManager"
    status_mgr: "StatusManager | None"
    message_scratch: MessageScratch
    status_scratch: StatusDocumentScratch
    narrative_outcome: "StagedNarrativeOutcome | None" = None
    plot_schedule_decisions: tuple["StagedPlotScheduleDecision", ...] = ()

    def commit(self) -> list[StatusDocumentChange]:
        snapshot = self.session.history
        try:
            if self.session.history_enabled:
                gateway = self.session._require_data_session()
                with gateway.database.atomic():
                    self._append_messages()
                    self._commit_narrative_outcome(gateway)
                    self._commit_plot_schedule(gateway)
                    changes = self.status_scratch.commit(self.status_mgr)
            else:
                # Non-persistent sessions are test/in-memory mode. They restore
                # message history on failure, but do not promise compensating
                # rollback for external status managers already written here.
                self._append_messages()
                changes = self.status_scratch.commit(self.status_mgr)
        except Exception as exc:
            if isinstance(exc, InvalidTurnMetadataError):
                logger.opt(exception=exc).error(
                    _TAG + " commit rejected invalid turn metadata; restoring in-memory history: session_id={}, staged={}",
                    getattr(self.session, "_session_id", ""),
                    self._staged_turn_metadata(),
                )
            else:
                logger.opt(exception=exc).error(_TAG + " commit failed; restoring in-memory history")
            self.session.replace_history(snapshot, persist=False)
            raise
        return changes

    def _append_messages(self) -> None:
        for message in self.message_scratch.staged_messages:
            self.session.append(
                message.role,
                message.content,
                mode=message.mode,
                turn_id=message.turn_id,
                seq_in_turn=message.seq_in_turn,
            )

    def _commit_narrative_outcome(self, gateway) -> None:
        staged = self.narrative_outcome
        if staged is None:
            return
        gateway.narrative_outcomes.record(
            session_id=self.session.session_id,
            turn_id=self.message_scratch.turn_id,
            outcome_code=staged.outcome_code,
            reason=staged.reason,
            actor=staged.actor,
            sample_value=staged.sample_value,
            effective_weights=staged.effective_weights,
            effective_source=staged.effective_source,
        )

    def _commit_plot_schedule(self, gateway) -> None:
        if not self.plot_schedule_decisions:
            return
        gateway.plot_scheduling.record_decisions(
            self.session.session_id,
            self.message_scratch.turn_id,
            self.plot_schedule_decisions,
        )

    def _staged_turn_metadata(self) -> list[dict[str, object]]:
        return [
            {
                "role": str(message.role),
                "turn_id": int(message.turn_id),
                "seq_in_turn": int(message.seq_in_turn),
            }
            for message in self.message_scratch.staged_messages
        ]
