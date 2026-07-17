"""Public transport-neutral protocol types for Agent requests and streams."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

from llm_client.types import LLMUsage
from rpg_core.agent.telemetry import TurnStats


class StreamEventKind(str, Enum):
    """Semantic event kinds emitted by an Agent stream."""

    TEXT = "text"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ROUND_START = "round_start"
    ROUND_END = "round_end"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentStreamEvent:
    """Transport-neutral semantic event emitted by ``send_stream``."""

    kind: StreamEventKind
    content: str = ""
    error_code: str | None = None
    status_code: int | None = None
    tool_name: str | None = None
    tool_arguments: str | None = None
    tool_call_id: str | None = None
    tool_result: str | None = None
    tool_result_preview: str | None = None
    round_index: int = 0
    usage: LLMUsage | None = None
    model: str | None = None
    finish_reason: str | None = None
    duration_ms: float = 0.0
    committed_turn_id: int | None = None
    reasoning_content: str | None = None
    stats: TurnStats | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"kind": self.kind.value}
        if self.content:
            data["content"] = self.content
        if self.error_code:
            data["error_code"] = self.error_code
        if self.status_code:
            data["status_code"] = int(self.status_code)
        if self.tool_name:
            data["tool_name"] = self.tool_name
        if self.tool_arguments:
            data["tool_arguments"] = self.tool_arguments
        if self.tool_result_preview:
            data["tool_result_preview"] = self.tool_result_preview
        if self.tool_result:
            data["tool_result"] = self.tool_result
        if self.round_index:
            data["round_index"] = self.round_index
        if self.usage:
            from rpg_core.context.usage import usage_to_wire_payload

            data["usage"] = usage_to_wire_payload(
                self.usage,
                model=self.model,
                finish_reason=self.finish_reason,
                duration_ms=self.duration_ms or None,
            )
        if self.duration_ms:
            data["duration_ms"] = round(self.duration_ms, 1)
        if self.model:
            data["model"] = self.model
        if self.finish_reason:
            data["finish_reason"] = self.finish_reason
        if self.committed_turn_id is not None:
            if self.committed_turn_id <= 0:
                raise ValueError("committed_turn_id must be a positive integer")
            data["committed_turn_id"] = int(self.committed_turn_id)
        return data


class TurnCancelStatus(StrEnum):
    """Result status for best-effort turn cancellation."""

    CANCELLED = "cancelled"
    NOT_RUNNING = "not_running"
    STALE = "stale"


@dataclass(frozen=True)
class TurnCancelResult:
    """Best-effort cancellation outcome for one Agent turn."""

    status: TurnCancelStatus
    session_id: str
    request_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "status": self.status.value,
            "session_id": self.session_id,
        }
        if self.request_id:
            data["request_id"] = self.request_id
        return data
