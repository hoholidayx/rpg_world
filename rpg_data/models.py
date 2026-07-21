"""Pure data models exposed by the RPG World data module."""

from __future__ import annotations

from dataclasses import dataclass

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
from rpg_data.model.narrative_outcome import (
    NARRATIVE_OUTCOME_CODES,
    NARRATIVE_OUTCOME_SOURCE_CONFIG,
    NARRATIVE_OUTCOME_SOURCE_SESSION,
    NARRATIVE_OUTCOME_SOURCE_STORY,
    NarrativeOutcomeCreate,
    NarrativeOutcomeRecord,
    NarrativeOutcomeWeights,
)
from rpg_data.model.composer import (
    NarrativeStyle,
    StoryNarrativeStyle,
    StoryQuickReply,
    WorkspaceTurnMode,
    WorkspaceTurnModeSeed,
)
from rpg_data.model.media import (
    MEDIA_ASSET_ORIGINS,
    MEDIA_ASSET_ORIGIN_GENERATED,
    MEDIA_ASSET_ORIGIN_UPLOAD,
    MEDIA_BACKGROUND_EVALUATION_STATUSES,
    MEDIA_BACKGROUND_EVALUATION_STATUS_FAILED,
    MEDIA_BACKGROUND_EVALUATION_STATUS_INTERRUPTED,
    MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED,
    MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING,
    MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL,
    MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED,
    MEDIA_BACKGROUND_EVALUATION_STATUS_SUPERSEDED,
    MEDIA_BACKGROUND_SOURCES,
    MEDIA_BACKGROUND_SOURCE_AUTO,
    MEDIA_BACKGROUND_SOURCE_MANUAL,
    MEDIA_JOB_ACTIVE_STATUSES,
    MEDIA_JOB_FINAL_STATUSES,
    MEDIA_JOB_STATUSES,
    MEDIA_JOB_STATUS_CANCELLED,
    MEDIA_JOB_STATUS_CANCELLING,
    MEDIA_JOB_STATUS_FAILED,
    MEDIA_JOB_STATUS_INTERRUPTED,
    MEDIA_JOB_STATUS_QUEUED,
    MEDIA_JOB_STATUS_RUNNING,
    MEDIA_JOB_STATUS_SUCCEEDED,
    MEDIA_LIBRARY_SCOPES,
    MEDIA_LIBRARY_SCOPE_STORY,
    MEDIA_LIBRARY_SCOPE_WORKSPACE,
    MEDIA_LIBRARY_TYPES,
    MEDIA_LIBRARY_TYPE_AVATAR,
    MEDIA_LIBRARY_TYPE_BACKGROUND,
    MEDIA_LIBRARY_TYPE_CHARACTER_SPRITE,
    MEDIA_LIBRARY_TYPE_ITEM,
    MEDIA_LIBRARY_TYPE_MAP,
    MEDIA_LIBRARY_TYPE_OTHER,
    MEDIA_LIBRARY_TYPE_REFERENCE,
    MEDIA_LIBRARY_TYPE_SCENE_ILLUSTRATION,
    MEDIA_LIBRARY_TYPE_UI,
    MediaAsset,
    MediaAssetDeleteResult,
    MediaAssetOrigin,
    MediaBackgroundEvaluation,
    MediaBackgroundEvaluationStatus,
    MediaBackgroundSource,
    MediaBlob,
    MediaDisplayAssetBundle,
    MediaJob,
    MediaJobCompletion,
    MediaJobCompletionWrite,
    MediaJobStatus,
    MediaLibraryAssetBundle,
    MediaLibraryBatchFailure,
    MediaLibraryBatchResult,
    MediaLibraryFacetValue,
    MediaLibraryFacets,
    MediaLibraryItem,
    MediaLibraryPage,
    MediaLibraryReconcileResult,
    MediaLibraryScope,
    MediaLibrarySearchWeights,
    MediaLibraryStoryFacet,
    MediaLibraryType,
    MediaLibraryUsage,
    MediaSourceMessage,
    MediaSourceTurn,
    SessionMediaAssetBundle,
    SessionMediaBackground,
    SessionMediaBackgroundState,
    SessionMediaGalleryItem,
    SessionMediaResetResult,
)
from rpg_data.model.rp_modules import (
    RPModuleCatalogEntry,
    SessionRPModuleOverride,
    SessionRPModuleSelectionRows,
    StoryRPModule,
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
from rpg_data.model.tts import (
    TTS_JOB_ACTIVE_STATUSES,
    TTS_JOB_FINAL_STATUSES,
    TTS_JOB_STATUSES,
    TTS_JOB_STATUS_FAILED,
    TTS_JOB_STATUS_INTERRUPTED,
    TTS_JOB_STATUS_QUEUED,
    TTS_JOB_STATUS_RUNNING,
    TTS_JOB_STATUS_SUCCEEDED,
    TTSAudioPart,
    TTSBlob,
    TTSCacheEntry,
    TTSCompletedPart,
    TTSJob,
    TTSJobCompletionWrite,
    TTSJobStatus,
    TTSMessageSource,
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
    "MediaJobCompletionWrite",
    "MediaJobStatus",
    "MediaLibraryAssetBundle",
    "MediaLibraryBatchFailure",
    "MediaLibraryBatchResult",
    "MediaLibraryFacetValue",
    "MediaLibraryFacets",
    "MediaLibraryPage",
    "MediaLibraryReconcileResult",
    "MediaLibraryStoryFacet",
    "MediaLibraryUsage",
    "MediaLibrarySearchWeights",
    "MediaLibraryScope",
    "MediaLibraryType",
    "MediaAssetOrigin",
    "MediaBackgroundSource",
    "MediaBackgroundEvaluationStatus",
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
    "TTSCompletedPart",
    "TTSJobCompletionWrite",
    "TTSJobStatus",
    "TTS_JOB_ACTIVE_STATUSES",
    "TTS_JOB_FINAL_STATUSES",
    "NarrativeOutcomeRecord",
    "NarrativeOutcomeCreate",
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
    "SessionRPModuleSelectionRows",
    "WorkspaceTurnMode",
    "WorkspaceTurnModeSeed",
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
