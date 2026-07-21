"""Commit plan for one successful agent turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ContextManager, Protocol, TYPE_CHECKING

from loguru import logger

from rpg_core.agent.turn.transaction.message_scratch import MessageScratch
from rpg_core.agent.turn.transaction.status_scratch import StatusDocumentChange, StatusDocumentScratch
from rpg_core.rp_modules.narrative_outcome.ledger import NarrativeOutcomeLedgerService
from rpg_core.rp_modules.plot_scheduler.ledger import PlotScheduleLedgerService
from rpg_core.session import InvalidTurnMetadataError

if TYPE_CHECKING:
    from rpg_data.models import StagedPlotScheduleDecision
    from rpg_core.rp_modules.narrative_outcome.models import StagedNarrativeOutcome
    from rpg_core.session import SessionManager
    from rpg_core.status.manager import StatusManager

_TAG = "[AgentTurnTransaction]"


class TurnCommitTransactionPort(Protocol):
    def transaction(self) -> ContextManager[None]: ...


@dataclass
class TurnCommitPlan:
    """Durable writes produced by a successful agent turn."""

    session: "SessionManager"
    status_mgr: "StatusManager | None"
    message_scratch: MessageScratch
    status_scratch: StatusDocumentScratch
    transaction_data: TurnCommitTransactionPort | None = None
    narrative_outcome_ledger: NarrativeOutcomeLedgerService | None = None
    plot_schedule_ledger: PlotScheduleLedgerService | None = None
    narrative_outcome: "StagedNarrativeOutcome | None" = None
    plot_schedule_decisions: tuple["StagedPlotScheduleDecision", ...] = ()

    def commit(self) -> list[StatusDocumentChange]:
        snapshot = self.session.history
        try:
            if self.session.history_enabled:
                if self.transaction_data is None:
                    raise RuntimeError("persistent turn commit requires transaction data")
                with self.transaction_data.transaction():
                    self._append_messages()
                    self._commit_narrative_outcome()
                    self._commit_plot_schedule()
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

    def _commit_narrative_outcome(self) -> None:
        staged = self.narrative_outcome
        if staged is None:
            return
        if self.narrative_outcome_ledger is None:
            raise RuntimeError("Narrative Outcome ledger is not configured")
        self.narrative_outcome_ledger.record(
            self.session.session_id,
            self.message_scratch.turn_id,
            staged,
        )

    def _commit_plot_schedule(self) -> None:
        if not self.plot_schedule_decisions:
            return
        if self.plot_schedule_ledger is None:
            raise RuntimeError("Plot Schedule ledger is not configured")
        self.plot_schedule_ledger.record(
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


__all__ = ["TurnCommitPlan", "TurnCommitTransactionPort"]
