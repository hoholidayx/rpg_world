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
