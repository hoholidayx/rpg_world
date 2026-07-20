"""Canonical typed persistence contracts for Media storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rpg_data.model.session import MESSAGE_ROLES


class MediaJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class MediaAssetOrigin(StrEnum):
    GENERATED = "generated"
    UPLOAD = "upload"


class MediaLibraryScope(StrEnum):
    STORY = "story"
    WORKSPACE = "workspace"


class MediaLibraryType(StrEnum):
    BACKGROUND = "background"
    AVATAR = "avatar"
    CHARACTER_SPRITE = "character_sprite"
    SCENE_ILLUSTRATION = "scene_illustration"
    MAP = "map"
    ITEM = "item"
    UI = "ui"
    REFERENCE = "reference"
    OTHER = "other"


class MediaBackgroundSource(StrEnum):
    MANUAL = "manual"
    AUTO = "auto"


class MediaBackgroundEvaluationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    SKIPPED_MANUAL = "skipped_manual"
    INTERRUPTED = "interrupted"


MEDIA_JOB_STATUS_QUEUED = MediaJobStatus.QUEUED
MEDIA_JOB_STATUS_RUNNING = MediaJobStatus.RUNNING
MEDIA_JOB_STATUS_CANCELLING = MediaJobStatus.CANCELLING
MEDIA_JOB_STATUS_SUCCEEDED = MediaJobStatus.SUCCEEDED
MEDIA_JOB_STATUS_FAILED = MediaJobStatus.FAILED
MEDIA_JOB_STATUS_CANCELLED = MediaJobStatus.CANCELLED
MEDIA_JOB_STATUS_INTERRUPTED = MediaJobStatus.INTERRUPTED
MEDIA_JOB_STATUSES = frozenset(MediaJobStatus)
MEDIA_JOB_ACTIVE_STATUSES = frozenset({
    MediaJobStatus.QUEUED,
    MediaJobStatus.RUNNING,
    MediaJobStatus.CANCELLING,
})
MEDIA_JOB_FINAL_STATUSES = MEDIA_JOB_STATUSES - MEDIA_JOB_ACTIVE_STATUSES

MEDIA_ASSET_ORIGIN_GENERATED = MediaAssetOrigin.GENERATED
MEDIA_ASSET_ORIGIN_UPLOAD = MediaAssetOrigin.UPLOAD
MEDIA_ASSET_ORIGINS = frozenset(MediaAssetOrigin)

MEDIA_LIBRARY_SCOPE_STORY = MediaLibraryScope.STORY
MEDIA_LIBRARY_SCOPE_WORKSPACE = MediaLibraryScope.WORKSPACE
MEDIA_LIBRARY_SCOPES = frozenset(MediaLibraryScope)

MEDIA_LIBRARY_TYPE_BACKGROUND = MediaLibraryType.BACKGROUND
MEDIA_LIBRARY_TYPE_AVATAR = MediaLibraryType.AVATAR
MEDIA_LIBRARY_TYPE_CHARACTER_SPRITE = MediaLibraryType.CHARACTER_SPRITE
MEDIA_LIBRARY_TYPE_SCENE_ILLUSTRATION = MediaLibraryType.SCENE_ILLUSTRATION
MEDIA_LIBRARY_TYPE_MAP = MediaLibraryType.MAP
MEDIA_LIBRARY_TYPE_ITEM = MediaLibraryType.ITEM
MEDIA_LIBRARY_TYPE_UI = MediaLibraryType.UI
MEDIA_LIBRARY_TYPE_REFERENCE = MediaLibraryType.REFERENCE
MEDIA_LIBRARY_TYPE_OTHER = MediaLibraryType.OTHER
MEDIA_LIBRARY_TYPES = frozenset(MediaLibraryType)

MEDIA_BACKGROUND_SOURCE_MANUAL = MediaBackgroundSource.MANUAL
MEDIA_BACKGROUND_SOURCE_AUTO = MediaBackgroundSource.AUTO
MEDIA_BACKGROUND_SOURCES = frozenset(MediaBackgroundSource)

MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED = MediaBackgroundEvaluationStatus.QUEUED
MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING = MediaBackgroundEvaluationStatus.RUNNING
MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED = MediaBackgroundEvaluationStatus.SUCCEEDED
MEDIA_BACKGROUND_EVALUATION_STATUS_FAILED = MediaBackgroundEvaluationStatus.FAILED
MEDIA_BACKGROUND_EVALUATION_STATUS_SUPERSEDED = MediaBackgroundEvaluationStatus.SUPERSEDED
MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL = (
    MediaBackgroundEvaluationStatus.SKIPPED_MANUAL
)
MEDIA_BACKGROUND_EVALUATION_STATUS_INTERRUPTED = (
    MediaBackgroundEvaluationStatus.INTERRUPTED
)
MEDIA_BACKGROUND_EVALUATION_STATUSES = frozenset(MediaBackgroundEvaluationStatus)


@dataclass(frozen=True)
class MediaSourceMessage:
    id: int
    version: int
    role: str
    content: str
    turn_id: int
    seq_in_turn: int

    def __post_init__(self) -> None:
        if self.id <= 0 or self.version <= 0:
            raise ValueError("media source message identity must be positive")
        if self.role not in MESSAGE_ROLES:
            raise ValueError(f"invalid media source message role: {self.role}")
        if self.turn_id <= 0 or self.seq_in_turn <= 0:
            raise ValueError("media source turn metadata must be positive")


@dataclass(frozen=True)
class MediaSourceTurn:
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


@dataclass(frozen=True)
class MediaLibraryUsage:
    background_references: int = 0
    gallery_references: int = 0


@dataclass(frozen=True)
class MediaLibrarySearchWeights:
    """Caller-selected weights for an efficient library search read model."""

    exact_tag: int
    title_contains: int
    description_contains: int


@dataclass(frozen=True)
class MediaLibraryAssetBundle:
    item: MediaLibraryItem
    asset: MediaAsset
    blob: MediaBlob
    tags: tuple[str, ...] = field(default_factory=tuple)
    usage: MediaLibraryUsage = field(default_factory=MediaLibraryUsage)


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
class MediaJobCompletionWrite:
    """Caller-prepared values used by the atomic Media completion primitive."""

    workspace_id: str
    story_id: int
    sha256: str
    canonical_ext: str
    mime_type: str
    byte_size: int
    relative_path: str
    provider_asset_id: str
    metadata_json: str
    library_title: str
    library_description: str
    library_tags: tuple[str, ...]


__all__ = [name for name in globals() if name.startswith("MEDIA_") or name.startswith("Media") or name.startswith("SessionMedia")]
