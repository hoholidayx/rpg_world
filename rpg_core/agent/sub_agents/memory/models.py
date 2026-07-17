"""Typed results and failures for memory SubAgent workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from rpg_core.agent.telemetry import CallRecord


class MemoryPipelineError(RuntimeError):
    """Raised when a failed pipeline must leave progress retryable."""


@dataclass
class MemoryAgentResult:
    """Result returned by ``MemorySubAgent.process``."""

    story_details_added: int = 0
    summary_generated: bool = False
    skipped: bool = False
    call_stats: list[CallRecord] = field(default_factory=list)


class StoryMemoryExtractionStatus(str, Enum):
    """Terminal state of a pending story-memory extraction run."""

    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class StoryMemoryExtractionResult:
    """Typed result shared by command, post-commit, and derivation callers."""

    status: StoryMemoryExtractionStatus
    pending_turns: int = 0
    completed_turns: int = 0
    completed_batches: int = 0
    story_details_added: int = 0
    call_stats: tuple[CallRecord, ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is StoryMemoryExtractionStatus.SUCCEEDED

    @property
    def failed(self) -> bool:
        return self.status is StoryMemoryExtractionStatus.FAILED
