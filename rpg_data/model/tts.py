"""Canonical typed persistence contracts for TTS storage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TTSJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


TTS_JOB_STATUS_QUEUED = TTSJobStatus.QUEUED
TTS_JOB_STATUS_RUNNING = TTSJobStatus.RUNNING
TTS_JOB_STATUS_SUCCEEDED = TTSJobStatus.SUCCEEDED
TTS_JOB_STATUS_FAILED = TTSJobStatus.FAILED
TTS_JOB_STATUS_INTERRUPTED = TTSJobStatus.INTERRUPTED
TTS_JOB_STATUSES = frozenset(TTSJobStatus)
TTS_JOB_ACTIVE_STATUSES = frozenset({
    TTSJobStatus.QUEUED,
    TTSJobStatus.RUNNING,
})
TTS_JOB_FINAL_STATUSES = TTS_JOB_STATUSES - TTS_JOB_ACTIVE_STATUSES


@dataclass(frozen=True)
class TTSBlob:
    id: str
    workspace_id: str
    sha256: str
    mime_type: str
    byte_size: int
    relative_path: str
    created_at: str = ""


@dataclass(frozen=True)
class TTSCacheEntry:
    id: str
    workspace_id: str
    source_fingerprint: str
    config_fingerprint: str
    normalization_revision: str
    part_count: int
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class TTSAudioPart:
    id: str
    cache_entry_id: str
    blob_id: str
    part_index: int
    created_at: str = ""


@dataclass(frozen=True)
class TTSJob:
    id: str
    session_id: str
    message_id: int
    status: TTSJobStatus
    source_fingerprint: str
    config_fingerprint: str
    normalization_revision: str
    cache_entry_id: str | None = None
    error_code: str = ""
    error_message: str = ""
    started_at: str = ""
    finished_at: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", TTSJobStatus(self.status))


@dataclass(frozen=True)
class TTSMessageSource:
    session_id: str
    message_id: int
    workspace_id: str
    workspace_root: str
    role: str
    content: str
    turn_id: int
    seq_in_turn: int


@dataclass(frozen=True)
class TTSCompletedPart:
    sha256: str
    byte_size: int
    relative_path: str


@dataclass(frozen=True)
class TTSJobCompletionWrite:
    """Caller-prepared identity and audio parts for atomic completion."""

    workspace_id: str
    source_fingerprint: str
    config_fingerprint: str
    normalization_revision: str
    parts: tuple[TTSCompletedPart, ...]
    status: TTSJobStatus = TTSJobStatus.SUCCEEDED

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", TTSJobStatus(self.status))


__all__ = [
    "TTSAudioPart",
    "TTSBlob",
    "TTSCacheEntry",
    "TTSCompletedPart",
    "TTSJob",
    "TTSJobCompletionWrite",
    "TTSJobStatus",
    "TTSMessageSource",
    "TTS_JOB_STATUSES",
    "TTS_JOB_ACTIVE_STATUSES",
    "TTS_JOB_FINAL_STATUSES",
    "TTS_JOB_STATUS_FAILED",
    "TTS_JOB_STATUS_INTERRUPTED",
    "TTS_JOB_STATUS_QUEUED",
    "TTS_JOB_STATUS_RUNNING",
    "TTS_JOB_STATUS_SUCCEEDED",
]
