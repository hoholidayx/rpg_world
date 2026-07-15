"""Pure data models exposed by the RPG World data module."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Mapping

__all__ = [
    "Character",
    "CharacterDetail",
    "LorebookEntry",
    "MediaAsset",
    "MediaAssetDeleteResult",
    "MediaBlob",
    "MediaJob",
    "MediaJobCompletion",
    "MediaSourceMessage",
    "MediaSourceTurn",
    "SessionMediaBackground",
    "SessionMediaAssetBundle",
    "SessionMediaGalleryItem",
    "SessionMediaResetResult",
    "NarrativeOutcomeRecord",
    "NarrativeOutcomeWeights",
    "RPModuleCatalogEntry",
    "SessionRPModuleOverride",
    "Session",
    "SessionCharacter",
    "SessionCharacterDetail",
    "SessionLorebookEntry",
    "SessionMessage",
    "SessionPlayerCharacterSnapshot",
    "SessionProfile",
    "SessionDeleteResult",
    "SessionResetResult",
    "SessionStatusResetResult",
    "SessionStoryMemory",
    "SessionStatusTable",
    "Story",
    "StoryRPModule",
    "NarrativeStyle",
    "StoryNarrativeStyle",
    "StoryQuickReply",
    "WorkspaceTurnMode",
    "StoryCharacter",
    "StoryLorebookEntry",
    "StoryLorebookEntryDetail",
    "StoryStatusTable",
    "StatusRowRef",
    "StatusTableData",
    "StatusDeferredProgress",
    "StatusTableDocument",
    "StatusTableRow",
    "StatusTableTemplate",
    "STATUS_KIND_NORMAL",
    "STATUS_KIND_SCENE",
    "STATUS_ORIGIN_SESSION_NATIVE",
    "STATUS_ORIGIN_TEMPLATE_COPY",
    "STATUS_KEY_COLUMN",
    "STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE",
    "STORY_STATUS_MOUNT_ORIGIN_SYSTEM",
    "STATUS_TABLE_KIND",
    "STATUS_TABLE_MODE_KEY_VALUE",
    "STATUS_VALUE_COLUMN",
    "STATUS_UPDATE_FREQUENCIES",
    "STATUS_UPDATE_FREQUENCY_DEFERRED",
    "STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN",
    "STATUS_UPDATE_FREQUENCY_MANUAL",
    "STATUS_UPDATE_FREQUENCY_REALTIME",
    "STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY",
    "STATUS_ROW_UPDATE_FREQUENCY_KEY",
    "STATUS_ROW_UPDATE_RULE_KEY",
    "MESSAGE_ROLE_ASSISTANT",
    "MESSAGE_ROLE_SYSTEM",
    "MESSAGE_ROLE_TOOL",
    "MESSAGE_ROLE_USER",
    "MESSAGE_ROLES",
    "MEDIA_JOB_ACTIVE_STATUSES",
    "MEDIA_JOB_FINAL_STATUSES",
    "MEDIA_JOB_STATUSES",
    "MEDIA_JOB_STATUS_CANCELLED",
    "MEDIA_JOB_STATUS_CANCELLING",
    "MEDIA_JOB_STATUS_FAILED",
    "MEDIA_JOB_STATUS_INTERRUPTED",
    "MEDIA_JOB_STATUS_QUEUED",
    "MEDIA_JOB_STATUS_RUNNING",
    "MEDIA_JOB_STATUS_SUCCEEDED",
    "TURN_MODE_GM",
    "TURN_MODE_IC",
    "TURN_MODE_OOC",
    "TURN_MODES",
    "NARRATIVE_OUTCOME_CODES",
    "NARRATIVE_OUTCOME_SOURCE_CONFIG",
    "NARRATIVE_OUTCOME_SOURCE_SESSION",
    "NARRATIVE_OUTCOME_SOURCE_STORY",
    "PLAYER_CHARACTER_STATUS_BOUND",
    "PLAYER_CHARACTER_STATUS_INVALID",
    "SESSION_RUNTIME_CLEANUP_ABSENT",
    "SESSION_RUNTIME_CLEANUP_DELETED",
    "SESSION_RUNTIME_CLEANUP_PENDING",
    "Workspace",
    "parse_status_document",
    "serialize_status_document",
    "validate_story_status_mount_origin",
    "validate_status_kind",
    "validate_status_update_policy",
]

STATUS_TABLE_KIND = "status_table"
STATUS_TABLE_MODE_KEY_VALUE = "key_value"
PLAYER_CHARACTER_STATUS_BOUND = "bound"
PLAYER_CHARACTER_STATUS_INVALID = "invalid"
SESSION_RUNTIME_CLEANUP_DELETED = "deleted"
SESSION_RUNTIME_CLEANUP_ABSENT = "absent"
SESSION_RUNTIME_CLEANUP_PENDING = "pending"
STATUS_KIND_SCENE = "scene"
STATUS_KIND_NORMAL = "normal"
STATUS_ORIGIN_TEMPLATE_COPY = "template_copy"
STATUS_ORIGIN_SESSION_NATIVE = "session_native"
STORY_STATUS_MOUNT_ORIGIN_SYSTEM = "system_mount"
STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE = "story_template"
STATUS_KEY_COLUMN = "属性"
STATUS_VALUE_COLUMN = "值"
STATUS_UPDATE_FREQUENCY_REALTIME = "realtime"
STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN = "event_driven"
STATUS_UPDATE_FREQUENCY_DEFERRED = "deferred"
STATUS_UPDATE_FREQUENCY_MANUAL = "manual"
STATUS_UPDATE_FREQUENCIES = frozenset({
    STATUS_UPDATE_FREQUENCY_REALTIME,
    STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
    STATUS_UPDATE_FREQUENCY_DEFERRED,
    STATUS_UPDATE_FREQUENCY_MANUAL,
})
STATUS_ROW_UPDATE_FREQUENCY_KEY = "updateFrequency"
STATUS_ROW_UPDATE_RULE_KEY = "updateRule"
STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY = "deferredIntervalTurns"
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
MEDIA_JOB_STATUS_QUEUED = "queued"
MEDIA_JOB_STATUS_RUNNING = "running"
MEDIA_JOB_STATUS_CANCELLING = "cancelling"
MEDIA_JOB_STATUS_SUCCEEDED = "succeeded"
MEDIA_JOB_STATUS_FAILED = "failed"
MEDIA_JOB_STATUS_CANCELLED = "cancelled"
MEDIA_JOB_STATUS_INTERRUPTED = "interrupted"
MEDIA_JOB_STATUSES = frozenset({
    MEDIA_JOB_STATUS_QUEUED,
    MEDIA_JOB_STATUS_RUNNING,
    MEDIA_JOB_STATUS_CANCELLING,
    MEDIA_JOB_STATUS_SUCCEEDED,
    MEDIA_JOB_STATUS_FAILED,
    MEDIA_JOB_STATUS_CANCELLED,
    MEDIA_JOB_STATUS_INTERRUPTED,
})
MEDIA_JOB_ACTIVE_STATUSES = frozenset({
    MEDIA_JOB_STATUS_QUEUED,
    MEDIA_JOB_STATUS_RUNNING,
    MEDIA_JOB_STATUS_CANCELLING,
})
MEDIA_JOB_FINAL_STATUSES = MEDIA_JOB_STATUSES - MEDIA_JOB_ACTIVE_STATUSES
TURN_MODE_IC = "ic"
TURN_MODE_OOC = "ooc"
TURN_MODE_GM = "gm"
TURN_MODES = frozenset({TURN_MODE_IC, TURN_MODE_OOC, TURN_MODE_GM})
NARRATIVE_OUTCOME_CODES = (
    "critical_success",
    "success",
    "success_with_cost",
    "setback",
    "critical_failure",
)
NARRATIVE_OUTCOME_SOURCE_CONFIG = "config"
NARRATIVE_OUTCOME_SOURCE_STORY = "story"
NARRATIVE_OUTCOME_SOURCE_SESSION = "session"


@dataclass(frozen=True)
class NarrativeOutcomeWeights:
    critical_success: int = 5
    success: int = 25
    success_with_cost: int = 40
    setback: int = 25
    critical_failure: int = 5

    def __post_init__(self) -> None:
        values = self.values()
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("narrative outcome weights must be integers")
        if any(value < 0 or value > 100 for value in values):
            raise ValueError("narrative outcome weights must be within [0, 100]")
        if sum(values) != 100:
            raise ValueError("narrative outcome weights must sum to 100")

    def values(self) -> tuple[int, int, int, int, int]:
        return (
            self.critical_success,
            self.success,
            self.success_with_cost,
            self.setback,
            self.critical_failure,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "critical_success": self.critical_success,
            "success": self.success,
            "success_with_cost": self.success_with_cost,
            "setback": self.setback,
            "critical_failure": self.critical_failure,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "NarrativeOutcomeWeights":
        keys = set(raw)
        expected = set(NARRATIVE_OUTCOME_CODES)
        if keys != expected:
            missing = sorted(expected - keys)
            unexpected = sorted(keys - expected)
            raise ValueError(
                "narrative outcome weights must contain exactly five codes; "
                f"missing={missing}, unexpected={unexpected}"
            )
        return cls(
            critical_success=_weight_int(raw.get("critical_success"), "critical_success"),
            success=_weight_int(raw.get("success"), "success"),
            success_with_cost=_weight_int(raw.get("success_with_cost"), "success_with_cost"),
            setback=_weight_int(raw.get("setback"), "setback"),
            critical_failure=_weight_int(raw.get("critical_failure"), "critical_failure"),
        )


@dataclass(frozen=True)
class NarrativeOutcomeRecord:
    id: int
    session_id: str
    turn_id: int
    outcome_code: str
    reason: str
    actor: str
    sample_value: int
    effective_weights: NarrativeOutcomeWeights
    effective_source: str
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.outcome_code not in NARRATIVE_OUTCOME_CODES:
            raise ValueError(f"invalid narrative outcome code: {self.outcome_code}")
        if self.turn_id <= 0:
            raise ValueError("turn_id must be positive")
        if not 1 <= self.sample_value <= 100:
            raise ValueError("sample_value must be within [1, 100]")
        if self.effective_source not in {
            NARRATIVE_OUTCOME_SOURCE_CONFIG,
            NARRATIVE_OUTCOME_SOURCE_STORY,
            NARRATIVE_OUTCOME_SOURCE_SESSION,
        }:
            raise ValueError(
                f"invalid narrative outcome source: {self.effective_source}"
            )


def _weight_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"narrative outcome weight {name} must be an integer")
    return value


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    root_path: str
    description: str = ""
    enabled: bool = True
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class WorkspaceTurnMode:
    workspace_id: str
    mode: str
    short_name: str
    prompt: str = ""
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class NarrativeStyle:
    id: int
    workspace_id: str
    name: str
    prompt: str = ""
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryNarrativeStyle:
    id: int
    workspace_id: str
    story_id: int
    narrative_style_id: int
    name: str
    prompt: str = ""
    is_base: bool = False
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryQuickReply:
    id: int
    workspace_id: str
    story_id: int
    title: str
    message: str = ""
    sort_order: int = 0
    enabled: bool = True
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class RPModuleCatalogEntry:
    module_name: str
    display_name: str
    description: str = ""
    sort_order: int = 0
    config_version: int = 1
    default_story_enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryRPModule:
    id: int
    story_id: int
    module_name: str
    enabled: bool = True
    config: Mapping[str, object] = field(default_factory=dict)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionRPModuleOverride:
    id: int
    session_id: str
    module_name: str
    enabled: bool | None = None
    config: Mapping[str, object] = field(default_factory=dict)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Story:
    id: int
    workspace_id: str
    title: str
    summary: str = ""
    # Story-level fixed system prompt injected through the fixed layer.
    story_prompt: str = ""
    first_message: str = ""
    main_llm_provider_key: str | None = None
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Session:
    id: str
    workspace_id: str
    story_id: int
    state_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    title: str = ""
    description: str = ""
    main_llm_provider_key: str | None = None
    player_character_id: int | None = None
    player_character_snapshot_json: str = "{}"
    profile_metadata_json: str = "{}"
    profile_created_at: str = ""
    profile_updated_at: str = ""


@dataclass(frozen=True)
class SessionProfile:
    session_id: str
    title: str = ""
    description: str = ""
    main_llm_provider_key: str | None = None
    player_character_id: int | None = None
    player_character_snapshot_json: str = "{}"
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionDeleteResult:
    """Result of permanently deleting one catalog session."""

    session_id: str
    runtime_cleanup: str


@dataclass(frozen=True)
class SessionResetResult:
    """Counts produced by one atomic reset of session-owned runtime data."""

    session_id: str
    messages_cleared: int = 0
    narrative_outcomes_cleared: int = 0
    story_memories_cleared: int = 0
    template_status_tables_cleared: int = 0
    template_status_tables_initialized: int = 0
    session_native_status_tables_reset: int = 0
    deferred_progress_cleared: int = 0
    media_jobs_cleared: int = 0
    media_gallery_items_cleared: int = 0
    media_backgrounds_cleared: int = 0
    first_message: str = ""


@dataclass(frozen=True)
class SessionStatusResetResult:
    """Counts produced by resetting one session's status-table runtime."""

    session_id: str
    template_tables_cleared: int = 0
    template_tables_initialized: int = 0
    native_tables_reset: int = 0
    deferred_progress_cleared: int = 0


@dataclass(frozen=True)
class MediaSourceMessage:
    """One immutable persisted-message component used by media source snapshots."""

    id: int
    version: int
    role: str
    content: str
    turn_id: int
    seq_in_turn: int

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("media source message id must be positive")
        if self.version <= 0:
            raise ValueError("media source message version must be positive")
        if self.role not in MESSAGE_ROLES:
            raise ValueError(f"invalid media source message role: {self.role}")
        if self.turn_id <= 0 or self.seq_in_turn <= 0:
            raise ValueError("media source turn metadata must be positive")


@dataclass(frozen=True)
class MediaSourceTurn:
    """Committed messages grouped under one positive turn id."""

    turn_id: int
    messages: tuple[MediaSourceMessage, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.turn_id <= 0:
            raise ValueError("media source turn id must be positive")
        if not self.messages:
            raise ValueError("media source turn must contain at least one message")
        if any(message.turn_id != self.turn_id for message in self.messages):
            raise ValueError("media source turn contains a message from another turn")


@dataclass(frozen=True)
class MediaBlob:
    id: str
    workspace_id: str
    sha256: str
    canonical_ext: str
    mime_type: str
    byte_size: int
    relative_path: str
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class MediaAsset:
    id: str
    workspace_id: str
    blob_id: str
    provider_key: str
    visual_brief_json: str
    provider_asset_id: str = ""
    generation_params_json: str = "{}"
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class MediaJob:
    id: str
    session_id: str
    provider_key: str
    status: str
    source_start_turn_id: int
    source_end_turn_id: int
    source_fingerprint: str
    source_snapshot_json: str
    visual_brief_json: str
    generation_params_json: str = "{}"
    output_asset_id: str | None = None
    retry_of_job_id: str | None = None
    error_code: str = ""
    error_message: str = ""
    started_at: str = ""
    finished_at: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in MEDIA_JOB_STATUSES:
            raise ValueError(f"invalid media job status: {self.status}")
        if self.source_start_turn_id <= 0:
            raise ValueError("media source start turn id must be positive")
        if self.source_end_turn_id < self.source_start_turn_id:
            raise ValueError("media source end turn id precedes start turn id")


@dataclass(frozen=True)
class SessionMediaGalleryItem:
    id: str
    session_id: str
    asset_id: str
    source_start_turn_id: int
    source_end_turn_id: int
    source_fingerprint: str
    source_snapshot_json: str
    visual_brief_json: str
    job_id: str | None = None
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionMediaBackground:
    session_id: str
    asset_id: str
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionMediaResetResult:
    session_id: str
    jobs_cleared: int = 0
    gallery_items_cleared: int = 0
    backgrounds_cleared: int = 0


@dataclass(frozen=True)
class MediaAssetDeleteResult:
    asset: MediaAsset
    blob: MediaBlob
    blob_deleted: bool


@dataclass(frozen=True)
class SessionMediaAssetBundle:
    gallery_item: SessionMediaGalleryItem
    asset: MediaAsset
    blob: MediaBlob


@dataclass(frozen=True)
class MediaJobCompletion:
    job: MediaJob
    asset: MediaAsset
    blob: MediaBlob
    gallery_item: SessionMediaGalleryItem
    blob_created: bool


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
            import json

            data["tool_calls"] = json.loads(self.tool_calls_json)
        return data


@dataclass(frozen=True)
class SessionStoryMemory:
    id: int
    session_id: str
    turn_id: int
    text: str = ""
    dream_processed: bool = False
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_context_dict(self) -> dict[str, object]:
        import json

        try:
            metadata = json.loads(self.metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        return {
            "id": self.id,
            "turn_id": self.turn_id,
            "text": self.text,
            "dream_processed": self.dream_processed,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }


@dataclass(frozen=True)
class Character:
    id: int
    workspace_id: str
    name: str
    personality: str = ""
    content: str = ""
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class CharacterDetail:
    id: int
    character_id: int
    name: str
    content: str = ""
    tags_json: str = "[]"
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class LorebookEntry:
    id: int
    workspace_id: str
    name: str
    content: str = ""
    description: str = ""
    tags_json: str = "[]"
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionLorebookEntry:
    id: int
    mount_id: int
    workspace_id: str
    story_id: int
    name: str
    content: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True)
class SessionCharacterDetail:
    id: int
    character_id: int
    name: str
    content: str = ""
    tags: tuple[str, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True)
class SessionCharacter:
    id: int
    mount_id: int
    workspace_id: str
    story_id: int
    name: str
    personality: str = ""
    content: str = ""
    details: tuple[SessionCharacterDetail, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True)
class StoryCharacter:
    id: int
    workspace_id: str
    story_id: int
    character_id: int
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryCharacterDetail:
    mount: StoryCharacter
    character: Character


@dataclass(frozen=True)
class StoryLorebookEntry:
    id: int
    workspace_id: str
    story_id: int
    lorebook_entry_id: int
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryLorebookEntryDetail:
    mount: StoryLorebookEntry
    entry: LorebookEntry


@dataclass(frozen=True)
class StatusRowRef:
    """Reference a status table row by index or by matching a cell value."""

    row_index: int | None = None
    match_column: int | str | None = None
    match_value: str | None = None

    @staticmethod
    def index(row_index: int) -> "StatusRowRef":
        return StatusRowRef(row_index=row_index)

    @staticmethod
    def match(column: int | str, value: str) -> "StatusRowRef":
        return StatusRowRef(match_column=column, match_value=str(value))


@dataclass(frozen=True)
class StatusTableData:
    """Immutable helper for reading and editing key-value status data."""

    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()

    def column_index(self, column: int | str) -> int:
        if isinstance(column, int):
            if column < 0 or column >= len(self.headers):
                raise IndexError(f"Status table column index out of range: {column}")
            return column
        name = str(column)
        try:
            return self.headers.index(name)
        except ValueError as exc:
            raise KeyError(f"Status table column not found: {name}") from exc

    def find_row_indexes(self, column: int | str, value: str) -> tuple[int, ...]:
        col = self.column_index(column)
        expected = str(value)
        return tuple(
            idx
            for idx, row in enumerate(self.rows)
            if col < len(row) and row[col] == expected
        )

    def row_index(self, ref: int | StatusRowRef) -> int:
        if isinstance(ref, int):
            return self._validate_row_index(ref)
        if ref.row_index is not None:
            return self._validate_row_index(ref.row_index)
        if ref.match_column is None or ref.match_value is None:
            raise ValueError("Status row reference must specify an index or match")
        matches = self.find_row_indexes(ref.match_column, ref.match_value)
        if not matches:
            raise FileNotFoundError(f"Status table row not found: {ref.match_value}")
        if len(matches) > 1:
            raise ValueError(f"Status table row match is ambiguous: {ref.match_value}")
        return matches[0]

    def cell(self, ref: int | StatusRowRef, column: int | str) -> str:
        row_idx = self.row_index(ref)
        col_idx = self.column_index(column)
        row = self.rows[row_idx]
        return row[col_idx] if col_idx < len(row) else ""

    def with_cell(
        self,
        ref: int | StatusRowRef,
        column: int | str,
        value: str,
    ) -> "StatusTableData":
        row_idx = self.row_index(ref)
        col_idx = self.column_index(column)
        rows = [list(self._normalize_row(row)) for row in self.rows]
        rows[row_idx][col_idx] = str(value)
        return StatusTableData(
            headers=self.headers,
            rows=tuple(tuple(row) for row in rows),
        )

    def with_appended_row(self, values: object) -> "StatusTableData":
        return StatusTableData(
            headers=self.headers,
            rows=self.rows + (self._normalize_row(values),),
        )

    def with_replaced_row(
        self,
        ref: int | StatusRowRef,
        values: object,
    ) -> "StatusTableData":
        row_idx = self.row_index(ref)
        rows = list(self.rows)
        rows[row_idx] = self._normalize_row(values)
        return StatusTableData(headers=self.headers, rows=tuple(rows))

    def with_deleted_row(self, ref: int | StatusRowRef) -> "StatusTableData":
        row_idx = self.row_index(ref)
        return StatusTableData(
            headers=self.headers,
            rows=tuple(row for idx, row in enumerate(self.rows) if idx != row_idx),
        )

    def with_key_value(
        self,
        key: str,
        value: str,
        key_column: int | str = STATUS_KEY_COLUMN,
        value_column: int | str = STATUS_VALUE_COLUMN,
    ) -> "StatusTableData":
        key_idx = self.column_index(key_column)
        value_idx = self.column_index(value_column)
        matches = self.find_row_indexes(key_idx, key)
        if len(matches) > 1:
            raise ValueError(f"Status table key is ambiguous: {key}")
        if matches:
            return self.with_cell(matches[0], value_idx, value)
        row = [""] * len(self.headers)
        row[key_idx] = str(key)
        row[value_idx] = str(value)
        return self.with_appended_row(row)

    def without_key(
        self,
        key: str,
        key_column: int | str = STATUS_KEY_COLUMN,
    ) -> "StatusTableData":
        matches = self.find_row_indexes(key_column, key)
        if not matches:
            raise FileNotFoundError(f"Status table key not found: {key}")
        if len(matches) > 1:
            raise ValueError(f"Status table key is ambiguous: {key}")
        return self.with_deleted_row(matches[0])

    def _validate_row_index(self, row_index: int) -> int:
        if row_index < 0 or row_index >= len(self.rows):
            raise IndexError(f"Status table row index out of range: {row_index}")
        return row_index

    def _normalize_row(self, values: object) -> tuple[str, ...]:
        if isinstance(values, (str, bytes)):
            raw = (str(values),)
        else:
            try:
                raw = tuple(str(item) for item in values)  # type: ignore[operator]
            except TypeError:
                raw = (str(values),)
        if not self.headers:
            return raw
        target_len = len(self.headers)
        if len(raw) < target_len:
            raw = raw + ("",) * (target_len - len(raw))
        return raw[:target_len]


@dataclass(frozen=True)
class StatusTableRow:
    key: str
    value: str
    runtime_key_locked: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)
    update_frequency: str = STATUS_UPDATE_FREQUENCY_REALTIME
    update_rule: str = ""
    deferred_interval_turns: int | None = None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "value": self.value,
            "runtimeKeyLocked": self.runtime_key_locked,
            "metadata": dict(self.metadata),
            STATUS_ROW_UPDATE_FREQUENCY_KEY: self.update_frequency,
            STATUS_ROW_UPDATE_RULE_KEY: self.update_rule,
            STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY: self.deferred_interval_turns,
        }


@dataclass(frozen=True)
class StatusDeferredProgress:
    session_status_table_id: int
    field_key: str
    last_processed_turn_id: int = 0


@dataclass(frozen=True)
class StatusTableDocument:
    schema_version: int = 1
    kind: str = STATUS_TABLE_KIND
    mode: str = STATUS_TABLE_MODE_KEY_VALUE
    key_column: str = STATUS_KEY_COLUMN
    value_column: str = STATUS_VALUE_COLUMN
    rows: tuple[StatusTableRow, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_rows(
        cls,
        *,
        key_column: str = STATUS_KEY_COLUMN,
        value_column: str = STATUS_VALUE_COLUMN,
        rows: tuple[StatusTableRow, ...] | list[StatusTableRow] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "StatusTableDocument":
        return cls(
            key_column=str(key_column or STATUS_KEY_COLUMN),
            value_column=str(value_column or STATUS_VALUE_COLUMN),
            rows=tuple(rows or ()),
            metadata=dict(metadata or {}),
        ).validated()

    @classmethod
    def from_data(
        cls,
        data: StatusTableData,
        *,
        locked_keys: set[str] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "StatusTableDocument":
        key_column = data.headers[0] if data.headers else STATUS_KEY_COLUMN
        value_column = data.headers[1] if len(data.headers) > 1 else STATUS_VALUE_COLUMN
        locked = locked_keys or set()
        rows = tuple(
            StatusTableRow(
                key=row[0] if row else "",
                value=row[1] if len(row) > 1 else "",
                runtime_key_locked=(row[0] if row else "") in locked,
            )
            for row in data.rows
        )
        return cls.from_rows(
            key_column=key_column,
            value_column=value_column,
            rows=rows,
            metadata=metadata,
        )

    @property
    def headers(self) -> tuple[str, str]:
        return (self.key_column, self.value_column)

    @property
    def data_rows(self) -> tuple[tuple[str, str], ...]:
        return tuple((row.key, row.value) for row in self.rows)

    def to_data(self) -> StatusTableData:
        return StatusTableData(headers=self.headers, rows=self.data_rows)

    def with_data(self, data: StatusTableData) -> "StatusTableDocument":
        rows_by_key = {row.key: row for row in self.rows}
        rows = tuple(
            StatusTableRow(
                key=row[0] if row else "",
                value=row[1] if len(row) > 1 else "",
                runtime_key_locked=(
                    rows_by_key[row[0]].runtime_key_locked
                    if row and row[0] in rows_by_key
                    else False
                ),
                metadata=(
                    dict(rows_by_key[row[0]].metadata)
                    if row and row[0] in rows_by_key
                    else {}
                ),
                update_frequency=(
                    rows_by_key[row[0]].update_frequency
                    if row and row[0] in rows_by_key
                    else STATUS_UPDATE_FREQUENCY_REALTIME
                ),
                update_rule=(
                    rows_by_key[row[0]].update_rule
                    if row and row[0] in rows_by_key
                    else ""
                ),
                deferred_interval_turns=(
                    rows_by_key[row[0]].deferred_interval_turns
                    if row and row[0] in rows_by_key
                    else None
                ),
            )
            for row in data.rows
        )
        key_column = data.headers[0] if data.headers else self.key_column
        value_column = data.headers[1] if len(data.headers) > 1 else self.value_column
        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=key_column,
            value_column=value_column,
            rows=rows,
            metadata=dict(self.metadata),
        ).validated()

    def with_key_value(self, key: str, value: str) -> "StatusTableDocument":
        expected = str(key)
        updated: list[StatusTableRow] = []
        matched = False
        for row in self.rows:
            if row.key == expected:
                updated.append(StatusTableRow(
                    row.key,
                    str(value),
                    row.runtime_key_locked,
                    dict(row.metadata),
                    row.update_frequency,
                    row.update_rule,
                    row.deferred_interval_turns,
                ))
                matched = True
            else:
                updated.append(row)
        if not matched:
            updated.append(StatusTableRow(expected, str(value), False, {}))
        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=self.key_column,
            value_column=self.value_column,
            rows=tuple(updated),
            metadata=dict(self.metadata),
        ).validated()

    def with_existing_values(
        self,
        updates: list[tuple[str, str]] | tuple[tuple[str, str], ...],
    ) -> "StatusTableDocument":
        """Return a copy with values replaced for existing keys only."""
        materialized = [(str(key), str(value)) for key, value in updates]
        if not materialized:
            raise ValueError("Status table value updates must not be empty")

        keys = [key for key, _value in materialized]
        if len(set(keys)) != len(keys):
            raise ValueError("Status table value updates contain duplicate keys")

        existing_keys = {row.key for row in self.rows}
        missing = [key for key in keys if key not in existing_keys]
        if missing:
            raise FileNotFoundError(f"Status table key not found: {missing[0]}")

        values_by_key = dict(materialized)
        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=self.key_column,
            value_column=self.value_column,
            rows=tuple(
                StatusTableRow(
                    row.key,
                    values_by_key.get(row.key, row.value),
                    row.runtime_key_locked,
                    dict(row.metadata),
                    row.update_frequency,
                    row.update_rule,
                    row.deferred_interval_turns,
                )
                for row in self.rows
            ),
            metadata=dict(self.metadata),
        ).validated()

    def with_cleared_values(self) -> "StatusTableDocument":
        """Return a copy with every value cleared and all structure preserved."""

        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=self.key_column,
            value_column=self.value_column,
            rows=tuple(
                StatusTableRow(
                    row.key,
                    "",
                    row.runtime_key_locked,
                    dict(row.metadata),
                    row.update_frequency,
                    row.update_rule,
                    row.deferred_interval_turns,
                )
                for row in self.rows
            ),
            metadata=dict(self.metadata),
        ).validated()

    def without_key(self, key: str) -> "StatusTableDocument":
        expected = str(key)
        if expected not in {row.key for row in self.rows}:
            raise FileNotFoundError(f"Status table key not found: {key}")
        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=self.key_column,
            value_column=self.value_column,
            rows=tuple(row for row in self.rows if row.key != expected),
            metadata=dict(self.metadata),
        ).validated()

    def row_for_key(self, key: str) -> StatusTableRow | None:
        expected = str(key)
        for row in self.rows:
            if row.key == expected:
                return row
        return None

    def validated(self) -> "StatusTableDocument":
        if self.kind != STATUS_TABLE_KIND:
            raise ValueError(f"Unsupported status table kind: {self.kind}")
        if self.mode != STATUS_TABLE_MODE_KEY_VALUE:
            raise ValueError(f"Unsupported status table mode: {self.mode}")
        seen: set[str] = set()
        for row in self.rows:
            if not row.key:
                raise ValueError("Status table row key must not be empty")
            if row.key in seen:
                raise ValueError(f"Status table key is duplicated: {row.key}")
            seen.add(row.key)
            validate_status_update_policy(
                row.update_frequency,
                update_rule=row.update_rule,
                deferred_interval_turns=row.deferred_interval_turns,
            )
        return self

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "kind": self.kind,
            "mode": self.mode,
            "keyColumn": self.key_column,
            "valueColumn": self.value_column,
            "rows": [row.to_json_dict() for row in self.rows],
            "metadata": dict(self.metadata),
        }


def parse_status_document(raw: str) -> StatusTableDocument:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Status table document JSON is invalid") from exc
    if not isinstance(data, dict):
        raise ValueError("Status table document must be an object")
    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list):
        raw_rows = []
    rows: list[StatusTableRow] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        raw_metadata = item.get("metadata", {})
        rows.append(StatusTableRow(
            key=str(item.get("key", "")),
            value=str(item.get("value", "")),
            runtime_key_locked=bool(item.get("runtimeKeyLocked", False)),
            metadata=raw_metadata if isinstance(raw_metadata, dict) else {},
            update_frequency=str(
                item.get(STATUS_ROW_UPDATE_FREQUENCY_KEY)
                or STATUS_UPDATE_FREQUENCY_REALTIME
            ),
            update_rule=str(item.get(STATUS_ROW_UPDATE_RULE_KEY) or ""),
            deferred_interval_turns=_parse_deferred_interval_turns(
                item.get(STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY)
            ),
        ))
    raw_metadata = data.get("metadata", {})
    return StatusTableDocument(
        schema_version=int(data.get("schemaVersion") or 1),
        kind=str(data.get("kind") or STATUS_TABLE_KIND),
        mode=str(data.get("mode") or STATUS_TABLE_MODE_KEY_VALUE),
        key_column=str(data.get("keyColumn") or STATUS_KEY_COLUMN),
        value_column=str(data.get("valueColumn") or STATUS_VALUE_COLUMN),
        rows=tuple(rows),
        metadata=raw_metadata if isinstance(raw_metadata, dict) else {},
    ).validated()


def _parse_deferred_interval_turns(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("deferredIntervalTurns must be a positive integer")
    return value


def serialize_status_document(document: StatusTableDocument) -> str:
    return json.dumps(document.validated().to_json_dict(), ensure_ascii=False, separators=(",", ":"))


def validate_status_kind(value: str) -> str:
    kind = str(value or STATUS_KIND_NORMAL)
    if kind not in {STATUS_KIND_SCENE, STATUS_KIND_NORMAL}:
        raise ValueError(f"Unsupported status kind: {kind}")
    return kind


def validate_status_update_policy(
    frequency: str,
    *,
    update_rule: str = "",
    deferred_interval_turns: int | None = None,
) -> str:
    normalized = str(frequency or STATUS_UPDATE_FREQUENCY_REALTIME).strip().lower()
    if normalized not in STATUS_UPDATE_FREQUENCIES:
        raise ValueError(f"Unsupported status update frequency: {normalized}")
    rule = str(update_rule or "").strip()
    if normalized == STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN and not rule:
        raise ValueError("event_driven status fields require updateRule")
    if normalized != STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN and rule:
        raise ValueError("updateRule is only supported for event_driven status fields")
    if deferred_interval_turns is not None:
        if (
            isinstance(deferred_interval_turns, bool)
            or not isinstance(deferred_interval_turns, int)
            or deferred_interval_turns <= 0
        ):
            raise ValueError("deferredIntervalTurns must be a positive integer")
        if normalized != STATUS_UPDATE_FREQUENCY_DEFERRED:
            raise ValueError(
                "deferredIntervalTurns is only supported for deferred status fields"
            )
    return normalized


def validate_story_status_mount_origin(value: str) -> str:
    origin = str(value or STORY_STATUS_MOUNT_ORIGIN_SYSTEM)
    if origin not in {STORY_STATUS_MOUNT_ORIGIN_SYSTEM, STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE}:
        raise ValueError(f"Unsupported story status mount origin: {origin}")
    return origin


@dataclass(frozen=True)
class StatusTableTemplate:
    id: int
    workspace_id: str
    name: str
    status_kind: str = STATUS_KIND_NORMAL
    description: str = ""
    document: StatusTableDocument = field(default_factory=StatusTableDocument)
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    @property
    def headers(self) -> tuple[str, str]:
        return self.document.headers

    @property
    def rows(self) -> tuple[tuple[str, str], ...]:
        return self.document.data_rows

    @property
    def data(self) -> StatusTableData:
        return self.document.to_data()

    def to_dict(self) -> dict[str, object]:
        return _status_table_as_dict(self)


@dataclass(frozen=True)
class StoryStatusTable:
    id: int
    workspace_id: str
    story_id: int
    status_table_id: int
    story_character_mount_id: int | None
    table_name: str
    mount_origin: str = STORY_STATUS_MOUNT_ORIGIN_SYSTEM
    status_kind: str = STATUS_KIND_NORMAL
    description: str = ""
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionStatusTable:
    id: int
    session_id: str
    workspace_id: str
    story_id: int
    source_table_id: int | None
    origin: str
    name: str
    status_kind: str = STATUS_KIND_NORMAL
    description: str = ""
    document: StatusTableDocument = field(default_factory=StatusTableDocument)
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    @property
    def headers(self) -> tuple[str, str]:
        return self.document.headers

    @property
    def rows(self) -> tuple[tuple[str, str], ...]:
        return self.document.data_rows

    @property
    def data(self) -> StatusTableData:
        return self.document.to_data()

    def to_dict(self) -> dict[str, object]:
        return _status_table_as_dict(self)


def _status_table_as_dict(table: object) -> dict[str, object]:
    data = asdict(table)
    data["document"] = table.document.to_json_dict()  # type: ignore[attr-defined]
    data["headers"] = list(table.headers)  # type: ignore[attr-defined]
    data["rows"] = [list(row) for row in table.rows]  # type: ignore[attr-defined]
    return data
