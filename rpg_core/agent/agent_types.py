"""Compatibility exports for the Agent protocol and telemetry types.

New core code imports canonical types from :mod:`rpg_core.agent.protocol`,
:mod:`rpg_core.agent.telemetry`, and :mod:`rpg_core.agent.mailbox.models`.
"""

from llm_client.types import LLMResponse, LLMUsage, ProviderChunk
from rpg_core.agent.mailbox.models import QueueItem, QueueKind, _StreamSentinel
from rpg_core.agent.protocol import (
    AgentStreamEvent,
    StreamEventKind,
    TurnCancelResult,
    TurnCancelStatus,
)
from rpg_core.agent.telemetry import CallRecord, TurnStats

__all__ = [
    "AgentStreamEvent",
    "CallRecord",
    "LLMResponse",
    "LLMUsage",
    "ProviderChunk",
    "QueueItem",
    "QueueKind",
    "StreamEventKind",
    "TurnCancelResult",
    "TurnCancelStatus",
    "TurnStats",
]
