"""Commit plan for one successful agent turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.transaction.message_scratch import MessageScratch
from rpg_core.agent.transaction.status_scratch import StatusDocumentChange, StatusDocumentScratch
from rpg_core.session import InvalidTurnMetadataError

if TYPE_CHECKING:
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

    def commit(self) -> list[StatusDocumentChange]:
        snapshot = self.session.history
        try:
            if self.session.history_enabled:
                gateway = self.session._require_data_session()
                with gateway.database.atomic():
                    self._append_messages()
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
                turn_id=message.turn_id,
                seq_in_turn=message.seq_in_turn,
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
