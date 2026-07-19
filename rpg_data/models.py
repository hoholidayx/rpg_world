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
    "MediaLibraryAssetBundle",
    "MediaLibraryBatchFailure",
    "MediaLibraryBatchResult",
    "MediaLibraryFacetValue",
    "MediaLibraryFacets",
    "MediaLibraryPage",
    "MediaLibraryReconcileResult",
    "MediaLibraryStoryFacet",
    "MediaLibraryUsage",
    "MediaDisplayAssetBundle",
    "MediaLibraryItem",
    "MediaBackgroundEvaluation",
    "MediaSourceMessage",
    "MediaSourceTurn",
    "SessionMediaBackground",
    "SessionMediaBackgroundState",
    "SessionMediaAssetBundle",
    "SessionMediaGalleryItem",
    "SessionMediaResetResult",
    "TTSJob",
    "TTSCacheEntry",
    "TTSAudioPart",
    "TTSBlob",
    "TTSMessageSource",
    "NarrativeOutcomeRecord",
    "NarrativeOutcomeWeights",
    "RPModuleCatalogEntry",
    "SessionRPModuleOverride",
    "Session",
    "SessionDerivationJob",
    "SessionDerivationSeedResult",
    "SessionCharacter",
    "SessionCharacterDetail",
    "SessionLorebookEntry",
    "SessionMessage",
    "SessionPlayerCharacterSnapshot",
    "SessionProfile",
    "SessionDeleteResult",
    "SessionResetResult",
    "SessionStatusResetResult",
    "MemoryFact",
    "MemoryEvidence",
    "SessionStoryMemory",
    "SessionStoryMemoryPage",
    "SessionStoryMemoryStats",
    "DreamApplyResult",
    "DreamEvidenceDraft",
    "DreamProposal",
    "DreamProposalItem",
    "DreamProposalItemDraft",
    "DreamProposalItemEvidence",
    "DreamProposalItemPatch",
    "DreamResetResult",
    "DreamSourceSnapshot",
    "DreamState",
    "PersistentMemory",
    "PersistentMemoryBundle",
    "PersistentMemoryEvidence",
    "PersistentMemoryRevision",
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
    "StatusBootstrapDocument",
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
    "STORY_MEMORY_KINDS",
    "STORY_MEMORY_EPISTEMIC_STATUSES",
    "DREAM_ACTIONS",
    "DREAM_ACTION_ADD",
    "DREAM_ACTION_RETIRE",
    "DREAM_ACTION_REVISE",
    "DREAM_ACTION_SUPERSEDE",
    "DREAM_DEPTHS",
    "DREAM_DEPTH_DEEP",
    "DREAM_DEPTH_SHALLOW",
    "DREAM_LIFECYCLES",
    "DREAM_LIFECYCLE_ACTIVE",
    "DREAM_LIFECYCLE_RETIRED",
    "DREAM_LIFECYCLE_SUPERSEDED",
    "DREAM_MAX_ACTIVE_MEMORIES",
    "DREAM_MAX_EVIDENCE_PER_ITEM",
    "DREAM_MAX_MEMORY_TEXT_CHARS",
    "DREAM_MAX_PROPOSAL_ITEMS",
    "DREAM_MAX_REASON_CHARS",
    "DREAM_PROPOSAL_STATUSES",
    "DREAM_PROPOSAL_STATUS_APPLIED",
    "DREAM_PROPOSAL_STATUS_FAILED",
    "DREAM_PROPOSAL_STATUS_GENERATING",
    "DREAM_PROPOSAL_STATUS_INTERRUPTED",
    "DREAM_PROPOSAL_STATUS_READY",
    "DREAM_PROPOSAL_STATUS_REJECTED",
    "DREAM_PROPOSAL_STATUS_STALE",
    "DREAM_SCOPES",
    "DREAM_SCOPE_FULL",
    "DREAM_SCOPE_INCREMENTAL",
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
    "MEDIA_ASSET_ORIGIN_GENERATED",
    "MEDIA_ASSET_ORIGIN_UPLOAD",
    "MEDIA_ASSET_ORIGINS",
    "MEDIA_LIBRARY_SCOPE_STORY",
    "MEDIA_LIBRARY_SCOPE_WORKSPACE",
    "MEDIA_LIBRARY_SCOPES",
    "MEDIA_LIBRARY_TYPE_AVATAR",
    "MEDIA_LIBRARY_TYPE_BACKGROUND",
    "MEDIA_LIBRARY_TYPE_CHARACTER_SPRITE",
    "MEDIA_LIBRARY_TYPE_ITEM",
    "MEDIA_LIBRARY_TYPE_MAP",
    "MEDIA_LIBRARY_TYPE_OTHER",
    "MEDIA_LIBRARY_TYPE_REFERENCE",
    "MEDIA_LIBRARY_TYPE_SCENE_ILLUSTRATION",
    "MEDIA_LIBRARY_TYPE_UI",
    "MEDIA_LIBRARY_TYPES",
    "MEDIA_BACKGROUND_SOURCE_MANUAL",
    "MEDIA_BACKGROUND_SOURCE_AUTO",
    "MEDIA_BACKGROUND_SOURCES",
    "MEDIA_BACKGROUND_EVALUATION_STATUSES",
    "MEDIA_BACKGROUND_EVALUATION_STATUS_FAILED",
    "MEDIA_BACKGROUND_EVALUATION_STATUS_INTERRUPTED",
    "MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED",
    "MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING",
    "MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL",
    "MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED",
    "MEDIA_BACKGROUND_EVALUATION_STATUS_SUPERSEDED",
    "TTS_JOB_STATUSES",
    "TTS_JOB_STATUS_QUEUED",
    "TTS_JOB_STATUS_RUNNING",
    "TTS_JOB_STATUS_SUCCEEDED",
    "TTS_JOB_STATUS_FAILED",
    "TTS_JOB_STATUS_INTERRUPTED",
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
    "SESSION_LIFECYCLE_PROVISIONING",
    "SESSION_LIFECYCLE_READY",
    "SESSION_DERIVATION_JOB_STATUSES",
    "SESSION_DERIVATION_JOB_STATUS_FAILED",
    "SESSION_DERIVATION_JOB_STATUS_INTERRUPTED",
    "SESSION_DERIVATION_JOB_STATUS_QUEUED",
    "SESSION_DERIVATION_JOB_STATUS_READY",
    "SESSION_DERIVATION_JOB_STATUS_RUNNING",
    "SESSION_DERIVATION_STAGES",
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
STORY_MEMORY_KINDS = frozenset({
    "character",
    "event",
    "relationship",
    "commitment",
    "clue",
    "world_fact",
    "state_change",
})
STORY_MEMORY_EPISTEMIC_STATUSES = frozenset({
    "confirmed",
    "reported",
    "inferred",
    "uncertain",
    "contradicted",
})
DREAM_DEPTH_SHALLOW = "shallow"
DREAM_DEPTH_DEEP = "deep"
DREAM_DEPTHS = frozenset({DREAM_DEPTH_SHALLOW, DREAM_DEPTH_DEEP})
DREAM_SCOPE_INCREMENTAL = "incremental"
DREAM_SCOPE_FULL = "full"
DREAM_SCOPES = frozenset({DREAM_SCOPE_INCREMENTAL, DREAM_SCOPE_FULL})
DREAM_PROPOSAL_STATUS_GENERATING = "generating"
DREAM_PROPOSAL_STATUS_READY = "ready"
DREAM_PROPOSAL_STATUS_APPLIED = "applied"
DREAM_PROPOSAL_STATUS_REJECTED = "rejected"
DREAM_PROPOSAL_STATUS_FAILED = "failed"
DREAM_PROPOSAL_STATUS_INTERRUPTED = "interrupted"
DREAM_PROPOSAL_STATUS_STALE = "stale"
DREAM_PROPOSAL_STATUSES = frozenset({
    DREAM_PROPOSAL_STATUS_GENERATING,
    DREAM_PROPOSAL_STATUS_READY,
    DREAM_PROPOSAL_STATUS_APPLIED,
    DREAM_PROPOSAL_STATUS_REJECTED,
    DREAM_PROPOSAL_STATUS_FAILED,
    DREAM_PROPOSAL_STATUS_INTERRUPTED,
    DREAM_PROPOSAL_STATUS_STALE,
})
DREAM_ACTION_ADD = "add"
DREAM_ACTION_REVISE = "revise"
DREAM_ACTION_SUPERSEDE = "supersede"
DREAM_ACTION_RETIRE = "retire"
DREAM_ACTIONS = frozenset({
    DREAM_ACTION_ADD,
    DREAM_ACTION_REVISE,
    DREAM_ACTION_SUPERSEDE,
    DREAM_ACTION_RETIRE,
})
DREAM_LIFECYCLE_ACTIVE = "active"
DREAM_LIFECYCLE_RETIRED = "retired"
DREAM_LIFECYCLE_SUPERSEDED = "superseded"
DREAM_LIFECYCLES = frozenset({
    DREAM_LIFECYCLE_ACTIVE,
    DREAM_LIFECYCLE_RETIRED,
    DREAM_LIFECYCLE_SUPERSEDED,
})
DREAM_MAX_ACTIVE_MEMORIES = 64
DREAM_MAX_MEMORY_TEXT_CHARS = 1000
DREAM_MAX_EVIDENCE_PER_ITEM = 64
DREAM_MAX_PROPOSAL_ITEMS = 128
DREAM_MAX_REASON_CHARS = 1000
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

TTS_JOB_STATUS_QUEUED = "queued"
TTS_JOB_STATUS_RUNNING = "running"
TTS_JOB_STATUS_SUCCEEDED = "succeeded"
TTS_JOB_STATUS_FAILED = "failed"
TTS_JOB_STATUS_INTERRUPTED = "interrupted"
TTS_JOB_STATUSES = frozenset({
    TTS_JOB_STATUS_QUEUED,
    TTS_JOB_STATUS_RUNNING,
    TTS_JOB_STATUS_SUCCEEDED,
    TTS_JOB_STATUS_FAILED,
    TTS_JOB_STATUS_INTERRUPTED,
})
MEDIA_ASSET_ORIGIN_GENERATED = "generated"
MEDIA_ASSET_ORIGIN_UPLOAD = "upload"
MEDIA_ASSET_ORIGINS = frozenset({
    MEDIA_ASSET_ORIGIN_GENERATED,
    MEDIA_ASSET_ORIGIN_UPLOAD,
})
MEDIA_LIBRARY_SCOPE_STORY = "story"
MEDIA_LIBRARY_SCOPE_WORKSPACE = "workspace"
MEDIA_LIBRARY_SCOPES = frozenset({
    MEDIA_LIBRARY_SCOPE_STORY,
    MEDIA_LIBRARY_SCOPE_WORKSPACE,
})
MEDIA_LIBRARY_TYPE_BACKGROUND = "background"
MEDIA_LIBRARY_TYPE_AVATAR = "avatar"
MEDIA_LIBRARY_TYPE_CHARACTER_SPRITE = "character_sprite"
MEDIA_LIBRARY_TYPE_SCENE_ILLUSTRATION = "scene_illustration"
MEDIA_LIBRARY_TYPE_MAP = "map"
MEDIA_LIBRARY_TYPE_ITEM = "item"
MEDIA_LIBRARY_TYPE_UI = "ui"
MEDIA_LIBRARY_TYPE_REFERENCE = "reference"
MEDIA_LIBRARY_TYPE_OTHER = "other"
MEDIA_LIBRARY_TYPES = frozenset({
    MEDIA_LIBRARY_TYPE_BACKGROUND,
    MEDIA_LIBRARY_TYPE_AVATAR,
    MEDIA_LIBRARY_TYPE_CHARACTER_SPRITE,
    MEDIA_LIBRARY_TYPE_SCENE_ILLUSTRATION,
    MEDIA_LIBRARY_TYPE_MAP,
    MEDIA_LIBRARY_TYPE_ITEM,
    MEDIA_LIBRARY_TYPE_UI,
    MEDIA_LIBRARY_TYPE_REFERENCE,
    MEDIA_LIBRARY_TYPE_OTHER,
})
MEDIA_BACKGROUND_SOURCE_MANUAL = "manual"
MEDIA_BACKGROUND_SOURCE_AUTO = "auto"
MEDIA_BACKGROUND_SOURCES = frozenset({
    MEDIA_BACKGROUND_SOURCE_MANUAL,
    MEDIA_BACKGROUND_SOURCE_AUTO,
})
MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED = "queued"
MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING = "running"
MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED = "succeeded"
MEDIA_BACKGROUND_EVALUATION_STATUS_FAILED = "failed"
MEDIA_BACKGROUND_EVALUATION_STATUS_SUPERSEDED = "superseded"
MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL = "skipped_manual"
MEDIA_BACKGROUND_EVALUATION_STATUS_INTERRUPTED = "interrupted"
MEDIA_BACKGROUND_EVALUATION_STATUSES = frozenset({
    MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED,
    MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING,
    MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED,
    MEDIA_BACKGROUND_EVALUATION_STATUS_FAILED,
    MEDIA_BACKGROUND_EVALUATION_STATUS_SUPERSEDED,
    MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL,
    MEDIA_BACKGROUND_EVALUATION_STATUS_INTERRUPTED,
})
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
    lifecycle: str = SESSION_LIFECYCLE_READY
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
class SessionDerivationSeedResult:
    job: SessionDerivationJob
    session: Session
    copied_message_count: int


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
    dream_memories_cleared: int = 0
    dream_proposals_cleared: int = 0
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
    origin_kind: str = MEDIA_ASSET_ORIGIN_GENERATED
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.origin_kind not in MEDIA_ASSET_ORIGINS:
            raise ValueError(f"invalid media asset origin: {self.origin_kind}")


@dataclass(frozen=True)
class MediaLibraryItem:
    id: str
    workspace_id: str
    asset_id: str
    scope: str
    story_id: int | None
    media_type: str
    title: str
    description: str
    is_default: bool = False
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.scope not in MEDIA_LIBRARY_SCOPES:
            raise ValueError(f"invalid media library scope: {self.scope}")
        if self.scope == MEDIA_LIBRARY_SCOPE_STORY and self.story_id is None:
            raise ValueError("story media library item requires story_id")
        if self.scope == MEDIA_LIBRARY_SCOPE_WORKSPACE and self.story_id is not None:
            raise ValueError("workspace media item must not bind a story")
        if self.media_type not in MEDIA_LIBRARY_TYPES:
            raise ValueError(f"invalid media library type: {self.media_type}")
        if self.scope != MEDIA_LIBRARY_SCOPE_STORY and self.is_default:
            raise ValueError("only story media items may be default backgrounds")
        if self.media_type != MEDIA_LIBRARY_TYPE_BACKGROUND and self.is_default:
            raise ValueError("only background media items may be story defaults")
        if not self.title.strip() or not self.description.strip():
            raise ValueError("media library title and description are required")


@dataclass(frozen=True)
class MediaLibraryAssetBundle:
    item: MediaLibraryItem
    asset: MediaAsset
    blob: MediaBlob
    tags: tuple[str, ...] = field(default_factory=tuple)
    usage: "MediaLibraryUsage" = field(default_factory=lambda: MediaLibraryUsage())


@dataclass(frozen=True)
class MediaLibraryUsage:
    background_references: int = 0
    gallery_references: int = 0


@dataclass(frozen=True)
class MediaLibraryPage:
    items: tuple[MediaLibraryAssetBundle, ...]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class MediaLibraryFacetValue:
    value: str
    count: int


@dataclass(frozen=True)
class MediaLibraryStoryFacet:
    story_id: int
    count: int


@dataclass(frozen=True)
class MediaLibraryFacets:
    media_types: tuple[MediaLibraryFacetValue, ...] = field(default_factory=tuple)
    tags: tuple[MediaLibraryFacetValue, ...] = field(default_factory=tuple)
    scopes: tuple[MediaLibraryFacetValue, ...] = field(default_factory=tuple)
    origins: tuple[MediaLibraryFacetValue, ...] = field(default_factory=tuple)
    stories: tuple[MediaLibraryStoryFacet, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MediaLibraryBatchFailure:
    item_id: str
    error_code: str
    message: str


@dataclass(frozen=True)
class MediaLibraryBatchResult:
    succeeded_item_ids: tuple[str, ...] = field(default_factory=tuple)
    failed: tuple[MediaLibraryBatchFailure, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MediaLibraryReconcileResult:
    workspace_id: str
    scanned_blobs: int = 0
    removed_blobs: int = 0
    removed_assets: int = 0
    removed_library_items: int = 0
    removed_gallery_items: int = 0
    cleared_backgrounds: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.scanned_blobs,
            self.removed_blobs,
            self.removed_assets,
            self.removed_library_items,
            self.removed_gallery_items,
            self.cleared_backgrounds,
        )
        if any(count < 0 for count in counts):
            raise ValueError("media library reconcile counts must not be negative")


@dataclass(frozen=True)
class MediaDisplayAssetBundle:
    asset: MediaAsset
    blob: MediaBlob
    library_item: MediaLibraryItem | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    gallery_item: SessionMediaGalleryItem | None = None


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
    status: str
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
        if self.status not in TTS_JOB_STATUSES:
            raise ValueError(f"invalid TTS job status: {self.status}")


@dataclass(frozen=True)
class TTSMessageSource:
    session_id: str
    message_id: int
    workspace_id: str
    workspace_root: str
    content: str


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
    source_mode: str = MEDIA_BACKGROUND_SOURCE_MANUAL
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.source_mode not in MEDIA_BACKGROUND_SOURCES:
            raise ValueError(f"invalid media background source: {self.source_mode}")


@dataclass(frozen=True)
class SessionMediaBackgroundState:
    session_id: str
    latest_observed_turn_id: int = 0
    latest_source_fingerprint: str = ""
    auto_suppressed: bool = False
    suppressed_through_turn_id: int = 0
    desired_turn_id: int = 0
    desired_source_fingerprint: str = ""
    last_applied_turn_id: int = 0
    last_applied_fingerprint: str = ""
    last_decision: str = ""
    last_reason: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class MediaBackgroundEvaluation:
    id: str
    session_id: str
    status: str
    target_turn_id: int
    source_fingerprint: str
    source_snapshot_json: str
    decision: str = ""
    selected_asset_id: str | None = None
    reason: str = ""
    error_code: str = ""
    error_message: str = ""
    started_at: str = ""
    finished_at: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in MEDIA_BACKGROUND_EVALUATION_STATUSES:
            raise ValueError(f"invalid media background evaluation status: {self.status}")
        if self.target_turn_id <= 0:
            raise ValueError("media background evaluation turn id must be positive")
        if len(self.source_fingerprint) != 64:
            raise ValueError("media background source fingerprint must be a SHA-256 digest")
        if self.decision not in {"", "keep", "switch"}:
            raise ValueError(f"invalid media background decision: {self.decision}")


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
class MemoryFact:
    """Common fact payload shared by Story and Persistent Memory projections."""

    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    dedupe_key: str


@dataclass(frozen=True)
class MemoryEvidence:
    """Immutable identity of one authoritative Session message."""

    message_id: int
    turn_id: int
    message_version: int
    content_hash: str


@dataclass(frozen=True)
class SessionStoryMemory:
    id: int
    session_id: str
    turn_id: int
    text: str = ""
    memory_kind: str = "event"
    epistemic_status: str = "confirmed"
    salience: float = 0.5
    source_turn_start: int = 0
    source_turn_end: int = 0
    dedupe_key: str = ""
    dream_processed: bool = False
    metadata_schema_version: int = 1
    metadata_json: str = "{}"
    evidence: tuple[MemoryEvidence, ...] = ()
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_context_dict(self) -> dict[str, object]:
        import json

        try:
            metadata = json.loads(self.metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        fact = self.fact
        return {
            "id": self.id,
            "turn_id": self.turn_id,
            "text": fact.text,
            "memory_kind": fact.memory_kind,
            "epistemic_status": fact.epistemic_status,
            "salience": fact.salience,
            "source_turn_start": self.source_turn_start,
            "source_turn_end": self.source_turn_end,
            "dedupe_key": self.dedupe_key,
            "dream_processed": self.dream_processed,
            "metadata_schema_version": self.metadata_schema_version,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }

    @property
    def fact(self) -> MemoryFact:
        return MemoryFact(
            text=self.text,
            memory_kind=self.memory_kind,
            epistemic_status=self.epistemic_status,
            salience=self.salience,
            dedupe_key=self.dedupe_key,
        )


@dataclass(frozen=True)
class SessionStoryMemoryStats:
    total_facts: int
    dream_processed_facts: int
    pending_dream_facts: int
    latest_updated_at: str = ""


@dataclass(frozen=True)
class SessionStoryMemoryPage:
    items: tuple[SessionStoryMemory, ...]
    page: int
    page_size: int
    total: int
    stats: SessionStoryMemoryStats


@dataclass(frozen=True)
class DreamEvidenceDraft(MemoryEvidence):
    """Evidence selected for a Dream proposal item."""


@dataclass(frozen=True)
class DreamProposalItemDraft:
    action: str
    dedupe_key: str
    text: str = ""
    memory_kind: str = "event"
    epistemic_status: str = "confirmed"
    salience: float = 0.5
    reason: str = ""
    target_memory_id: str | None = None
    base_revision_number: int | None = None
    selected: bool = True
    sort_order: int = 0
    evidence: tuple[DreamEvidenceDraft, ...] = ()


@dataclass(frozen=True)
class DreamProposalItemPatch:
    item_id: str
    selected: bool | None = None
    text: str | None = None
    memory_kind: str | None = None
    epistemic_status: str | None = None
    salience: float | None = None


@dataclass(frozen=True)
class DreamProposalItemEvidence:
    id: int
    proposal_item_id: str
    message_id: int
    turn_id: int
    message_version: int
    content_hash: str
    created_at: str = ""


@dataclass(frozen=True)
class DreamProposalItem:
    id: str
    proposal_id: str
    action: str
    dedupe_key: str
    selected: bool
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    reason: str = ""
    target_memory_id: str | None = None
    base_revision_number: int | None = None
    sort_order: int = 0
    evidence: tuple[DreamProposalItemEvidence, ...] = ()
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class DreamProposal:
    id: str
    session_id: str
    depth: str
    scope: str
    status: str
    history_fingerprint: str
    source_fingerprint: str
    ledger_revision: int
    next_messages_manifest_json: str = "{}"
    next_story_memories_manifest_json: str = "{}"
    next_summary_batches_manifest_json: str = "{}"
    source_story_memory_ids: tuple[int, ...] = ()
    error_code: str = ""
    error_message: str = ""
    items: tuple[DreamProposalItem, ...] = ()
    applied_at: str = ""
    rejected_at: str = ""
    finished_at: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class PersistentMemory:
    id: str
    session_id: str
    dedupe_key: str
    lifecycle: str
    current_revision_number: int
    superseded_by_memory_id: str | None = None
    created_from_proposal_id: str | None = None
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class PersistentMemoryEvidence(MemoryEvidence):
    id: int
    revision_id: int
    created_at: str = ""


@dataclass(frozen=True)
class PersistentMemoryRevision:
    id: int
    memory_id: str
    revision_number: int
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    source_proposal_id: str | None = None
    evidence: tuple[PersistentMemoryEvidence, ...] = ()
    created_at: str = ""


@dataclass(frozen=True)
class PersistentMemoryBundle:
    memory: PersistentMemory
    current_revision: PersistentMemoryRevision
    revisions: tuple[PersistentMemoryRevision, ...] = ()
    evidence_valid: bool = False

    @property
    def text(self) -> str:
        return self.current_revision.text

    @property
    def memory_kind(self) -> str:
        return self.current_revision.memory_kind

    @property
    def epistemic_status(self) -> str:
        return self.current_revision.epistemic_status

    @property
    def salience(self) -> float:
        return self.current_revision.salience

    @property
    def fact(self) -> MemoryFact:
        return MemoryFact(
            text=self.text,
            memory_kind=self.memory_kind,
            epistemic_status=self.epistemic_status,
            salience=self.salience,
            dedupe_key=self.memory.dedupe_key,
        )


@dataclass(frozen=True)
class DreamState:
    session_id: str
    ledger_revision: int = 0
    messages_manifest_json: str = "{}"
    story_memories_manifest_json: str = "{}"
    summary_batches_manifest_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class DreamApplyResult:
    proposal: DreamProposal
    ledger_revision: int
    active_memory_count: int
    created_memory_ids: tuple[str, ...] = ()
    revised_memory_ids: tuple[str, ...] = ()
    retired_memory_ids: tuple[str, ...] = ()
    superseded_memory_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DreamResetResult:
    session_id: str
    memories_cleared: int = 0
    proposals_cleared: int = 0
    states_cleared: int = 0


@dataclass(frozen=True)
class DreamSourceSnapshot:
    session_id: str
    messages: tuple[SessionMessage, ...]
    story_memories: tuple[SessionStoryMemory, ...]
    active_memories: tuple[PersistentMemoryBundle, ...]
    state: DreamState
    history_fingerprint: str
    story_memory_fingerprint: str


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
class StatusBootstrapDocument:
    """One status document staged by a derivation bootstrap."""

    table_id: int
    status_kind: str
    document: "StatusTableDocument"
    base_document: "StatusTableDocument"


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
