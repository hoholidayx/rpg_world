"""Typed storage contracts for the Session aggregate."""

from __future__ import annotations

import json
from dataclasses import dataclass

SESSION_LIFECYCLE_PROVISIONING = "provisioning"
SESSION_LIFECYCLE_READY = "ready"

SESSION_DERIVATION_JOB_STATUS_QUEUED = "queued"
SESSION_DERIVATION_JOB_STATUS_RUNNING = "running"
SESSION_DERIVATION_JOB_STATUS_READY = "ready"
SESSION_DERIVATION_JOB_STATUS_FAILED = "failed"
SESSION_DERIVATION_JOB_STATUS_INTERRUPTED = "interrupted"
SESSION_DERIVATION_JOB_STATUSES = frozenset({
    SESSION_DERIVATION_JOB_STATUS_QUEUED,
    SESSION_DERIVATION_JOB_STATUS_RUNNING,
    SESSION_DERIVATION_JOB_STATUS_READY,
    SESSION_DERIVATION_JOB_STATUS_FAILED,
    SESSION_DERIVATION_JOB_STATUS_INTERRUPTED,
})
SESSION_DERIVATION_STAGES = frozenset({
    "queued",
    "snapshotting",
    "copying",
    "rebuilding_status",
    "extracting_story_memory",
    "summarizing",
    "evaluating_context",
    "finalizing",
    "ready",
    "failed",
    "interrupted",
})

MESSAGE_ROLE_SYSTEM = "system"
MESSAGE_ROLE_USER = "user"
MESSAGE_ROLE_ASSISTANT = "assistant"
MESSAGE_ROLE_TOOL = "tool"
MESSAGE_ROLES = frozenset({
    MESSAGE_ROLE_SYSTEM,
    MESSAGE_ROLE_USER,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_TOOL,
})

TURN_MODE_IC = "ic"
TURN_MODE_OOC = "ooc"
TURN_MODE_GM = "gm"
TURN_MODES = frozenset({TURN_MODE_IC, TURN_MODE_OOC, TURN_MODE_GM})


@dataclass(frozen=True)
class Session:
    id: str
    workspace_id: str
    story_id: int
    state_json: str = "{}"
    lifecycle: str = SESSION_LIFECYCLE_READY
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    title: str = ""
    description: str = ""
    main_llm_provider_key: str | None = None
    player_character_id: int | None = None
    player_character_snapshot_json: str = "{}"
    story_opening_id: int | None = None
    profile_metadata_json: str = "{}"
    profile_created_at: str = ""
    profile_updated_at: str = ""


@dataclass(frozen=True)
class SessionDerivationJob:
    id: str
    source_session_id: str
    branch_turn_id: int
    requested_title: str = ""
    target_session_id: str | None = None
    status: str = SESSION_DERIVATION_JOB_STATUS_QUEUED
    stage: str = SESSION_DERIVATION_JOB_STATUS_QUEUED
    error_code: str = ""
    error_message: str = ""
    context_used_tokens: int | None = None
    context_limit: int | None = None
    context_threshold_exceeded: bool = False
    started_at: str = ""
    finished_at: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionDerivationJobUpdate:
    """Explicit fields for one derivation-ledger row update."""

    target_session_id: str | None = None
    status: str | None = None
    stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    context_used_tokens: int | None = None
    context_limit: int | None = None
    context_threshold_exceeded: bool | None = None
    write_context_usage: bool = False
    mark_started: bool = False
    mark_finished: bool = False


@dataclass(frozen=True)
class SessionProfile:
    session_id: str
    title: str = ""
    description: str = ""
    main_llm_provider_key: str | None = None
    player_character_id: int | None = None
    player_character_snapshot_json: str = "{}"
    story_opening_id: int | None = None
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionPlayerCharacterSnapshot:
    character_id: int
    mount_id: int
    story_id: int
    name: str
    avatar_url: str = ""
    role_label: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionCharacterMount:
    """Typed read projection for one character mounted on a Session's Story."""

    workspace_id: str
    story_id: int
    mount_id: int
    character_id: int
    name: str
    personality: str = ""
    content: str = ""
    metadata_json: str = "{}"
    character_updated_at: str = ""


@dataclass(frozen=True)
class SessionMessage:
    id: int
    session_id: str
    role: str
    content: str = ""
    mode: str = TURN_MODE_IC
    turn_id: int = 0
    seq_in_turn: int = 0
    tool_call_id: str = ""
    tool_calls_json: str = ""
    metadata_json: str = "{}"
    summary_processed: bool = False
    summary_batch_id: int | None = None
    summary_processed_at: str = ""
    story_memory_processed: bool = False
    story_memory_processed_at: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_message_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "role": self.role,
            "content": self.content,
            "mode": self.mode or TURN_MODE_IC,
        }
        if self.id:
            data["uid"] = self.id
        if self.turn_id:
            data["turn_id"] = self.turn_id
        if self.seq_in_turn:
            data["seq_in_turn"] = self.seq_in_turn
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.tool_calls_json:
            data["tool_calls"] = json.loads(self.tool_calls_json)
        return data


__all__ = [
    "MESSAGE_ROLES",
    "MESSAGE_ROLE_ASSISTANT",
    "MESSAGE_ROLE_SYSTEM",
    "MESSAGE_ROLE_TOOL",
    "MESSAGE_ROLE_USER",
    "SESSION_DERIVATION_JOB_STATUSES",
    "SESSION_DERIVATION_JOB_STATUS_FAILED",
    "SESSION_DERIVATION_JOB_STATUS_INTERRUPTED",
    "SESSION_DERIVATION_JOB_STATUS_QUEUED",
    "SESSION_DERIVATION_JOB_STATUS_READY",
    "SESSION_DERIVATION_JOB_STATUS_RUNNING",
    "SESSION_DERIVATION_STAGES",
    "SESSION_LIFECYCLE_PROVISIONING",
    "SESSION_LIFECYCLE_READY",
    "Session",
    "SessionCharacterMount",
    "SessionDerivationJob",
    "SessionDerivationJobUpdate",
    "SessionMessage",
    "SessionPlayerCharacterSnapshot",
    "SessionProfile",
    "TURN_MODE_GM",
    "TURN_MODE_IC",
    "TURN_MODE_OOC",
    "TURN_MODES",
]
