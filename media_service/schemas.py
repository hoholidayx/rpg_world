"""Typed media-service wire contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rpg_media.types import MEDIA_ASPECT_RATIOS, VisualBrief


class MediaSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class MediaHealthResponse(MediaSchema):
    status: Literal["ok"] = "ok"


class VisualBriefSchema(MediaSchema):
    scene_description: str = Field(alias="sceneDescription", min_length=1)
    subjects: list[str] = Field(default_factory=list)
    environment: str = ""
    action: str = ""
    composition: str = ""
    mood_lighting: str = Field(default="", alias="moodLighting")
    style: str = ""
    negative_constraints: str = Field(default="", alias="negativeConstraints")
    aspect_ratio: str = Field(default="16:9", alias="aspectRatio")

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, value: str) -> str:
        if value not in MEDIA_ASPECT_RATIOS:
            raise ValueError(f"aspectRatio must be one of {', '.join(MEDIA_ASPECT_RATIOS)}")
        return value

    def to_domain(self) -> VisualBrief:
        return VisualBrief(
            scene_description=self.scene_description,
            subjects=tuple(self.subjects),
            environment=self.environment,
            action=self.action,
            composition=self.composition,
            mood_lighting=self.mood_lighting,
            style=self.style,
            negative_constraints=self.negative_constraints,
            aspect_ratio=self.aspect_ratio,
        )

    @classmethod
    def from_domain(cls, brief: VisualBrief) -> "VisualBriefSchema":
        return cls.model_validate(brief.to_dict())


class MediaProviderResponse(MediaSchema):
    key: str
    display_name: str = Field(alias="displayName")
    kind: str
    available: bool
    reason: str = ""


class MediaProviderCatalogResponse(MediaSchema):
    default_key: str = Field(alias="defaultKey")
    providers: list[MediaProviderResponse]


class MediaSourceTurnResponse(MediaSchema):
    turn_id: int = Field(alias="turnId")
    roles: list[str]
    preview: str
    message_count: int = Field(alias="messageCount")


class MediaSourceTurnsResponse(MediaSchema):
    turns: list[MediaSourceTurnResponse]
    shortcuts: list[int] = Field(default_factory=lambda: [1, 5, 10, 20])
    max_turns: int = Field(default=20, alias="maxTurns")


class MediaBriefRequest(MediaSchema):
    start_turn_id: int = Field(alias="startTurnId", gt=0)
    end_turn_id: int = Field(alias="endTurnId", gt=0)


class MediaBriefResponse(MediaSchema):
    start_turn_id: int = Field(alias="startTurnId")
    end_turn_id: int = Field(alias="endTurnId")
    source_fingerprint: str = Field(alias="sourceFingerprint")
    brief: VisualBriefSchema


class MediaJobCreateRequest(MediaBriefRequest):
    provider_key: str | None = Field(default=None, alias="providerKey")
    source_fingerprint: str = Field(alias="sourceFingerprint", min_length=64, max_length=64)
    visual_brief: VisualBriefSchema = Field(alias="visualBrief")
    generation_params: dict[str, Any] = Field(default_factory=dict, alias="generationParams")


class MediaJobResponse(MediaSchema):
    job_id: str = Field(alias="jobId")
    session_id: str = Field(alias="sessionId")
    provider_key: str = Field(alias="providerKey")
    status: Literal[
        "queued",
        "running",
        "cancelling",
        "succeeded",
        "failed",
        "cancelled",
        "interrupted",
    ]
    start_turn_id: int = Field(alias="startTurnId")
    end_turn_id: int = Field(alias="endTurnId")
    source_fingerprint: str = Field(alias="sourceFingerprint")
    visual_brief: VisualBriefSchema = Field(alias="visualBrief")
    generation_params: dict[str, Any] = Field(alias="generationParams")
    output_asset_id: str | None = Field(alias="outputAssetId")
    retry_of_job_id: str | None = Field(alias="retryOfJobId")
    error_code: str = Field(alias="errorCode")
    error_message: str = Field(alias="errorMessage")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    started_at: str = Field(alias="startedAt")
    finished_at: str = Field(alias="finishedAt")


class MediaSourceReferenceResponse(MediaSchema):
    start_turn_id: int = Field(alias="startTurnId")
    end_turn_id: int = Field(alias="endTurnId")
    fingerprint: str
    stale: bool


class MediaGalleryItemResponse(MediaSchema):
    asset_id: str = Field(alias="assetId")
    job_id: str | None = Field(alias="jobId")
    provider_key: str = Field(alias="providerKey")
    sha256: str
    mime_type: str = Field(alias="mimeType")
    byte_size: int = Field(alias="byteSize")
    media_type: Literal[
        "background",
        "avatar",
        "character_sprite",
        "scene_illustration",
        "map",
        "item",
        "ui",
        "reference",
        "other",
    ] = Field(default="background", alias="mediaType")
    visual_brief: VisualBriefSchema = Field(alias="visualBrief")
    source: MediaSourceReferenceResponse
    created_at: str = Field(alias="createdAt")


class MediaGalleryResponse(MediaSchema):
    items: list[MediaGalleryItemResponse]
    active_jobs: list[MediaJobResponse] = Field(alias="activeJobs")
    recent_jobs: list[MediaJobResponse] = Field(default_factory=list, alias="recentJobs")


class MediaBackgroundSetRequest(MediaSchema):
    asset_id: str = Field(alias="assetId", min_length=1)


class MediaDisplayAssetResponse(MediaSchema):
    asset_id: str = Field(alias="assetId")
    library_item_id: str | None = Field(default=None, alias="libraryItemId")
    origin: Literal["generated", "upload"]
    mime_type: str = Field(alias="mimeType")
    byte_size: int = Field(alias="byteSize")
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(alias="createdAt")


class MediaBackgroundEvaluationRequest(MediaSchema):
    observed_turn_id: int = Field(alias="observedTurnId", gt=0)


class MediaBackgroundEvaluationResponse(MediaSchema):
    evaluation_id: str = Field(alias="evaluationId")
    session_id: str = Field(alias="sessionId")
    status: Literal[
        "queued",
        "running",
        "succeeded",
        "failed",
        "superseded",
        "skipped_manual",
        "interrupted",
    ]
    target_turn_id: int = Field(alias="targetTurnId")
    decision: Literal["", "keep", "switch"] = ""
    selected_asset_id: str | None = Field(default=None, alias="selectedAssetId")
    reason: str = ""
    error_code: str = Field(default="", alias="errorCode")
    error_message: str = Field(default="", alias="errorMessage")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    started_at: str = Field(default="", alias="startedAt")
    finished_at: str = Field(default="", alias="finishedAt")


class MediaBackgroundResponse(MediaSchema):
    background: MediaDisplayAssetResponse | None
    source_mode: Literal["none", "manual", "auto", "story_default"] = Field(
        alias="sourceMode"
    )
    manual_locked: bool = Field(alias="manualLocked")
    revision_token: str = Field(alias="revisionToken")
    last_decision: str = Field(default="", alias="lastDecision")
    last_reason: str = Field(default="", alias="lastReason")
    latest_evaluation: MediaBackgroundEvaluationResponse | None = Field(
        default=None,
        alias="latestEvaluation",
    )


class MediaLibraryUpdateRequest(MediaSchema):
    scope: Literal["story", "workspace"]
    story_id: int | None = Field(default=None, alias="storyId")
    media_type: Literal[
        "background",
        "avatar",
        "character_sprite",
        "scene_illustration",
        "map",
        "item",
        "ui",
        "reference",
        "other",
    ] = Field(alias="mediaType")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(min_length=1, max_length=20)
    is_default: bool = Field(default=False, alias="isDefault")


class MediaImageMetadataResponse(MediaSchema):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(min_length=1, max_length=20)


class MediaLibraryItemResponse(MediaSchema):
    item_id: str = Field(alias="itemId")
    asset_id: str = Field(alias="assetId")
    workspace_id: str = Field(alias="workspaceId")
    scope: Literal["story", "workspace"]
    story_id: int | None = Field(default=None, alias="storyId")
    media_type: Literal[
        "background",
        "avatar",
        "character_sprite",
        "scene_illustration",
        "map",
        "item",
        "ui",
        "reference",
        "other",
    ] = Field(alias="mediaType")
    title: str
    description: str
    tags: list[str]
    is_default: bool = Field(alias="isDefault")
    origin: Literal["generated", "upload"]
    mime_type: str = Field(alias="mimeType")
    byte_size: int = Field(alias="byteSize")
    background_references: int = Field(alias="backgroundReferences", ge=0)
    gallery_references: int = Field(alias="galleryReferences", ge=0)
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class MediaLibraryResponse(MediaSchema):
    items: list[MediaLibraryItemResponse]
    page: int = Field(ge=1)
    page_size: int = Field(alias="pageSize", ge=1, le=100)
    total: int = Field(ge=0)


class MediaLibraryFacetValueResponse(MediaSchema):
    value: str
    count: int = Field(ge=0)


class MediaLibraryStoryFacetResponse(MediaSchema):
    story_id: int = Field(alias="storyId")
    count: int = Field(ge=0)


class MediaLibraryFacetsResponse(MediaSchema):
    media_types: list[MediaLibraryFacetValueResponse] = Field(alias="mediaTypes")
    tags: list[MediaLibraryFacetValueResponse]
    scopes: list[MediaLibraryFacetValueResponse]
    origins: list[MediaLibraryFacetValueResponse]
    stories: list[MediaLibraryStoryFacetResponse]


class MediaLibraryBatchUpdateRequest(MediaSchema):
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=100)
    media_type: Literal[
        "background",
        "avatar",
        "character_sprite",
        "scene_illustration",
        "map",
        "item",
        "ui",
        "reference",
        "other",
    ] | None = Field(default=None, alias="mediaType")
    add_tags: list[str] = Field(default_factory=list, alias="addTags", max_length=20)
    remove_tags: list[str] = Field(default_factory=list, alias="removeTags", max_length=20)

    @field_validator("item_ids")
    @classmethod
    def validate_unique_item_ids(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item_id.strip() for item_id in value if item_id.strip()))
        if not normalized:
            raise ValueError("itemIds must contain at least one item")
        return normalized


class MediaLibraryBatchDeleteRequest(MediaSchema):
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=100)

    @field_validator("item_ids")
    @classmethod
    def validate_unique_item_ids(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item_id.strip() for item_id in value if item_id.strip()))
        if not normalized:
            raise ValueError("itemIds must contain at least one item")
        return normalized


class MediaLibraryBatchFailureResponse(MediaSchema):
    item_id: str = Field(alias="itemId")
    error_code: str = Field(alias="errorCode")
    message: str


class MediaLibraryBatchResponse(MediaSchema):
    succeeded_item_ids: list[str] = Field(alias="succeededItemIds")
    failed: list[MediaLibraryBatchFailureResponse]


class MediaLibraryReconcileResponse(MediaSchema):
    workspace_id: str = Field(alias="workspaceId")
    scanned_blobs: int = Field(alias="scannedBlobs", ge=0)
    removed_blobs: int = Field(alias="removedBlobs", ge=0)
    removed_assets: int = Field(alias="removedAssets", ge=0)
    removed_library_items: int = Field(alias="removedLibraryItems", ge=0)
    removed_gallery_items: int = Field(alias="removedGalleryItems", ge=0)
    cleared_backgrounds: int = Field(alias="clearedBackgrounds", ge=0)


class MediaLibraryDeleteResponse(MediaSchema):
    item_id: str = Field(alias="itemId")
    deleted: bool


class MediaAssetDeleteResponse(MediaSchema):
    asset_id: str = Field(alias="assetId")
    deleted: bool
