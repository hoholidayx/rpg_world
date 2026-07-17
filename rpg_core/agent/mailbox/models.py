"""Queue-owned data carriers for one session's Agent mailbox."""

from __future__ import annotations

from asyncio import Queue as AsyncQueue
from concurrent.futures import Future
from dataclasses import dataclass
from enum import StrEnum

from rpg_core.agent.turn.models import TurnRequest


class QueueKind(StrEnum):
    """Kinds of work serialized by ``AgentMailbox``."""

    SEND = "send"
    SEND_STREAM = "send_stream"
    COMMAND = "command"
    TRUNCATE_HISTORY = "truncate_history"
    MATERIALIZE_DERIVATION = "materialize_derivation"


@dataclass
class QueueItem:
    """One send, stream, command, truncate, or derivation mailbox item."""

    kind: QueueKind
    future: Future
    turn_request: TurnRequest | None = None
    command: str | None = None
    event_queue: AsyncQueue | None = None
    turn_id: int | None = None
    derivation_job_id: str | None = None

    @property
    def request_id(self) -> str | None:
        return self.turn_request.request_id if self.turn_request is not None else None

    @property
    def input_text(self) -> str:
        if self.turn_request is not None:
            return self.turn_request.text
        return self.command or ""


class _StreamSentinel:
    """Mark the end of one ``send_stream`` event queue."""

    pass
