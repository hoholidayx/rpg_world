"""Pure data models exposed by the RPG World data module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from rpg_data.plot_models import (
    PLOT_DECISION_DEFERRED,
    PLOT_DECISION_ERROR,
    PLOT_DECISION_PAGE_SIZE_MAX,
    PLOT_DECISION_STATUSES,
    PLOT_DECISION_TRIGGERED,
    PLOT_DISPATCH_FORCED,
    PLOT_DISPATCH_MODES,
    PLOT_DISPATCH_SOFT,
    PLOT_POOL_MODES,
    PLOT_POOL_RANDOM,
    PLOT_POOL_SEQUENTIAL,
    PLOT_SOURCE_KINDS,
    PLOT_SOURCE_OUTLINE,
    PLOT_SOURCE_POOL,
    SessionPlotOverrides,
    SessionPlotScheduleDecision,
    StagedPlotScheduleDecision,
    StoryPlotEvent,
    StoryPlotEventPool,
    StoryPlotOutline,
    StoryPlotOutlineNode,
    StoryPlotSchedule,
)
from rpg_data.model.memory import (
    DreamProposal,
    DreamProposalCreateValues,
    DreamProposalItem,
    DreamProposalItemEvidence,
    DreamProposalItemRowValues,
    DreamProposalRowUpdate,
    DreamResetResult,
    DreamState,
    DreamStateRowValues,
    MemoryEvidence,
    PersistentMemory,
    PersistentMemoryBundle,
    PersistentMemoryCreateValues,
    PersistentMemoryEvidence,
    PersistentMemoryRevision,
    PersistentMemoryRevisionCreateValues,
    PersistentMemoryRowUpdate,
    SessionStoryMemory,
    SessionStoryMemoryPage,
    SessionStoryMemoryStats,
    StoryMemoryRowValues,
)
from rpg_data.model.session import (
    MESSAGE_ROLES,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_SYSTEM,
    MESSAGE_ROLE_TOOL,
    MESSAGE_ROLE_USER,
    SESSION_DERIVATION_JOB_STATUSES,
    SESSION_DERIVATION_JOB_STATUS_FAILED,
    SESSION_DERIVATION_JOB_STATUS_INTERRUPTED,
    SESSION_DERIVATION_JOB_STATUS_QUEUED,
    SESSION_DERIVATION_JOB_STATUS_READY,
    SESSION_DERIVATION_JOB_STATUS_RUNNING,
    SESSION_DERIVATION_STAGES,
    SESSION_LIFECYCLE_PROVISIONING,
    SESSION_LIFECYCLE_READY,
    TURN_MODE_GM,
    TURN_MODE_IC,
    TURN_MODE_OOC,
    TURN_MODES,
    Session,
    SessionCharacterMount,
    SessionDerivationJob,
    SessionDerivationJobUpdate,
    SessionMessage,
    SessionPlayerCharacterSnapshot,
    SessionProfile,
)
from rpg_data.model.status import (
    STATUS_KEY_COLUMN,
    STATUS_KIND_NORMAL,
    STATUS_KIND_SCENE,
    STATUS_METADATA_STORY_MOUNT_KEY,
    STATUS_ORIGIN_SESSION_NATIVE,
    STATUS_ORIGIN_TEMPLATE_COPY,
    STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY,
    STATUS_ROW_UPDATE_FREQUENCY_KEY,
    STATUS_ROW_UPDATE_RULE_KEY,
    STATUS_TABLE_KIND,
    STATUS_TABLE_MODE_KEY_VALUE,
    STATUS_UPDATE_FREQUENCIES,
    STATUS_UPDATE_FREQUENCY_DEFERRED,
    STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
    STATUS_UPDATE_FREQUENCY_MANUAL,
    STATUS_UPDATE_FREQUENCY_REALTIME,
    STATUS_VALUE_COLUMN,
    STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE,
    STORY_STATUS_MOUNT_ORIGIN_SYSTEM,
    SessionStatusDocumentWrite,
    SessionStatusMetadata,
    SessionStatusResetPlan,
    SessionStatusResetResult,
    SessionStatusTable,
    StatusCharacterIdentity,
    StatusContextCandidate,
    StatusDeferredProgress,
    StatusDocumentBatchResult,
    StatusDocumentSaveResult,
    StatusDocumentWrite,
    StatusKind,
    StatusOrigin,
    StatusProgressWrite,
    StatusRowRef,
    StatusStoryMountIdentity,
    StatusTableData,
    StatusTableDocument,
    StatusTableRow,
    StatusTableTemplate,
    StatusUpdateFrequency,
    StoryStatusMountOrigin,
    StoryStatusMountSnapshot,
    StoryStatusTable,
    parse_session_status_metadata,
    parse_status_document,
    serialize_session_status_metadata,
    serialize_status_document,
    validate_status_kind,
    validate_status_origin,
    validate_status_update_policy,
    validate_story_status_mount_origin,
)

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
    "SessionPlotOverrides",
    "SessionPlotScheduleDecision",
    "StagedPlotScheduleDecision",
    "StoryPlotEvent",
    "StoryPlotEventPool",
    "StoryPlotOutline",
    "StoryPlotOutlineNode",
    "StoryPlotSchedule",
    "SessionRPModuleOverride",
    "Session",
    "SessionDerivationJob",
    "SessionDerivationJobUpdate",
    "SessionCharacter",
    "SessionCharacterMount",
    "SessionCharacterDetail",
    "SessionLorebookEntry",
    "SessionMessage",
    "SessionPlayerCharacterSnapshot",
    "SessionProfile",
    "SessionStatusResetResult",
    "SessionStatusResetPlan",
    "SessionStatusDocumentWrite",
    "SessionStatusMetadata",
    "MemoryEvidence",
    "StoryMemoryRowValues",
    "SessionStoryMemory",
    "SessionStoryMemoryPage",
    "SessionStoryMemoryStats",
    "DreamProposal",
    "DreamProposalCreateValues",
    "DreamProposalItem",
    "DreamProposalItemEvidence",
    "DreamProposalItemRowValues",
    "DreamProposalRowUpdate",
    "DreamResetResult",
    "DreamState",
    "DreamStateRowValues",
    "PersistentMemory",
    "PersistentMemoryBundle",
    "PersistentMemoryCreateValues",
    "PersistentMemoryEvidence",
    "PersistentMemoryRevision",
    "PersistentMemoryRevisionCreateValues",
    "PersistentMemoryRowUpdate",
    "SessionStatusTable",
    "Story",
    "StoryOpening",
    "StoryOpeningInput",
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
    "StatusCharacterIdentity",
    "StatusContextCandidate",
    "StatusDocumentBatchResult",
    "StatusDocumentSaveResult",
    "StatusDocumentWrite",
    "StatusKind",
    "StatusOrigin",
    "StatusProgressWrite",
    "StatusStoryMountIdentity",
    "StatusTableDocument",
    "StatusTableRow",
    "StatusTableTemplate",
    "StatusUpdateFrequency",
    "StoryStatusMountOrigin",
    "StoryStatusMountSnapshot",
    "STATUS_KIND_NORMAL",
    "PLOT_DECISION_DEFERRED",
    "PLOT_DECISION_ERROR",
    "PLOT_DECISION_PAGE_SIZE_MAX",
    "PLOT_DECISION_STATUSES",
    "PLOT_DECISION_TRIGGERED",
    "PLOT_DISPATCH_FORCED",
    "PLOT_DISPATCH_MODES",
    "PLOT_DISPATCH_SOFT",
    "PLOT_POOL_MODES",
    "PLOT_POOL_RANDOM",
    "PLOT_POOL_SEQUENTIAL",
    "PLOT_SOURCE_KINDS",
    "PLOT_SOURCE_OUTLINE",
    "PLOT_SOURCE_POOL",
    "STATUS_KIND_SCENE",
    "STATUS_METADATA_STORY_MOUNT_KEY",
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
    "MAX_STORY_OPENINGS",
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
    "parse_session_status_metadata",
    "serialize_session_status_metadata",
    "serialize_status_document",
    "validate_story_status_mount_origin",
    "validate_status_kind",
    "validate_status_origin",
    "validate_status_update_policy",
]

MAX_STORY_OPENINGS = 3
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
class StoryOpening:
    id: int
    workspace_id: str
    story_id: int
    title: str
    message: str
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryOpeningInput:
    title: str
    message: str
    id: int | None = None


@dataclass(frozen=True)
class Story:
    id: int
    workspace_id: str
    title: str
    summary: str = ""
    # Story-level fixed system prompt injected through the fixed layer.
    story_prompt: str = ""
    openings: tuple[StoryOpening, ...] = ()
    main_llm_provider_key: str | None = None
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""




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
