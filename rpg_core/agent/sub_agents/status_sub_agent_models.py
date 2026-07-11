"""Typed execution records owned by StatusSubAgent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rpg_core.agent.agent_types import CallRecord


class StatusSubAgentPreflightOutcome(StrEnum):
    """How Narrative Outcome was resolved for the current preflight."""

    STAGED = "staged"
    NONE = "none"
    FALLBACK = "fallback"


class StatusSubAgentRecordStatus(StrEnum):
    """Stable diagnostic states for a StatusSubAgent tool call."""

    CHANGED = "changed"
    NO_OP = "no_op"
    ERROR = "error"
    OUTCOME_STAGED = "outcome_staged"
    SKIPPED_DUE_TO_OUTCOME = "skipped_due_to_outcome"
    SKIPPED_DUPLICATE_OUTCOME = "skipped_duplicate_outcome"
    ROLLED_BACK_DUE_TO_FAILURE = "rolled_back_due_to_failure"

    @property
    def emits_tool_event(self) -> bool:
        """Whether this record represents a tool execution visible in SSE."""
        return self not in {
            StatusSubAgentRecordStatus.SKIPPED_DUE_TO_OUTCOME,
            StatusSubAgentRecordStatus.SKIPPED_DUPLICATE_OUTCOME,
            StatusSubAgentRecordStatus.ROLLED_BACK_DUE_TO_FAILURE,
        }

    @property
    def is_diagnostic_only(self) -> bool:
        return not self.emits_tool_event


class StatusSubAgentRecordText:
    """Canonical diagnostics for calls intentionally not executed or retained."""

    STATE_PREWRITE_SKIPPED = (
        "Skipped: rp_story_outcome was requested in the same preflight batch"
    )
    NON_OUTCOME_TOOL_SKIPPED = (
        "Skipped: only rp_story_outcome may execute in an outcome preflight batch"
    )
    DUPLICATE_OUTCOME_SKIPPED = (
        "Skipped: duplicate outcome call in the same preflight batch"
    )
    BATCH_ROLLBACK_SUFFIX = (
        " (rolled back because the preflight batch failed)"
    )


@dataclass
class StatusSubAgentToolRecord:
    """One typed StatusSubAgent tool decision and its execution result."""

    tool_name: str
    arguments: str
    result: str
    success: bool
    changed: bool
    status: StatusSubAgentRecordStatus

    @classmethod
    def skipped_due_to_outcome(
        cls,
        *,
        tool_name: str,
        arguments: str,
        state_prewrite: bool,
    ) -> "StatusSubAgentToolRecord":
        return cls(
            tool_name=tool_name,
            arguments=arguments,
            result=(
                StatusSubAgentRecordText.STATE_PREWRITE_SKIPPED
                if state_prewrite
                else StatusSubAgentRecordText.NON_OUTCOME_TOOL_SKIPPED
            ),
            success=False,
            changed=False,
            status=StatusSubAgentRecordStatus.SKIPPED_DUE_TO_OUTCOME,
        )

    @classmethod
    def skipped_duplicate_outcome(
        cls,
        *,
        tool_name: str,
        arguments: str,
    ) -> "StatusSubAgentToolRecord":
        return cls(
            tool_name=tool_name,
            arguments=arguments,
            result=StatusSubAgentRecordText.DUPLICATE_OUTCOME_SKIPPED,
            success=False,
            changed=False,
            status=StatusSubAgentRecordStatus.SKIPPED_DUPLICATE_OUTCOME,
        )

    def mark_rolled_back(self) -> None:
        """Convert a staged mutation into a diagnostic-only rollback record."""
        if not self.changed:
            return
        self.result = f"{self.result}{StatusSubAgentRecordText.BATCH_ROLLBACK_SUFFIX}"
        self.success = False
        self.changed = False
        self.status = StatusSubAgentRecordStatus.ROLLED_BACK_DUE_TO_FAILURE

    def to_payload(self) -> dict[str, object]:
        """Serialize at the AgentReply/SSE boundary without leaking enum objects."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result,
            "success": self.success,
            "changed": self.changed,
            "status": self.status.value,
        }


@dataclass
class StatusSubAgentResult:
    """StatusSubAgent result with typed tool-call diagnostics."""

    updated: bool = False
    records: list[StatusSubAgentToolRecord] = field(default_factory=list)
    call_stats: list[CallRecord] = field(default_factory=list)
    outcome_requested: bool = False
    outcome_staged: bool = False
    state_prewrites_skipped: int = 0
    failed: bool = False

    def record_payloads(self) -> list[dict[str, object]]:
        return [record.to_payload() for record in self.records]
