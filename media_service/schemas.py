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
    visual_brief: VisualBriefSchema = Field(alias="visualBrief")
    source: MediaSourceReferenceResponse
    created_at: str = Field(alias="createdAt")


class MediaGalleryResponse(MediaSchema):
    items: list[MediaGalleryItemResponse]
    active_jobs: list[MediaJobResponse] = Field(alias="activeJobs")
    recent_jobs: list[MediaJobResponse] = Field(default_factory=list, alias="recentJobs")


class MediaBackgroundSetRequest(MediaSchema):
    asset_id: str = Field(alias="assetId", min_length=1)


class MediaBackgroundResponse(MediaSchema):
    background: MediaGalleryItemResponse | None


class MediaAssetDeleteResponse(MediaSchema):
    asset_id: str = Field(alias="assetId")
    deleted: bool
