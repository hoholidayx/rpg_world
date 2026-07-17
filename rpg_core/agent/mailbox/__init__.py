"""FIFO and cancellation boundary for one session's Agent work."""

from rpg_core.agent.mailbox.models import QueueItem, QueueKind
from rpg_core.agent.mailbox.service import AgentMailbox, AgentMailboxClosedError

__all__ = [
    "AgentMailbox",
    "AgentMailboxClosedError",
    "QueueItem",
    "QueueKind",
]
