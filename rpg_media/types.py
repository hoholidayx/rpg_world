"""Framework-neutral media contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

from rpg_data import models

MEDIA_ASPECT_RATIOS = ("16:9", "3:2", "4:3", "1:1", "3:4", "9:16")


@dataclass(frozen=True)
class VisualBrief:
    scene_description: str
    subjects: tuple[str, ...] = field(default_factory=tuple)
    environment: str = ""
    action: str = ""
    composition: str = ""
    mood_lighting: str = ""
    style: str = ""
    negative_constraints: str = ""
    aspect_ratio: str = "16:9"

    def __post_init__(self) -> None:
        if not self.scene_description.strip():
            raise ValueError("sceneDescription is required")
        if self.aspect_ratio not in MEDIA_ASPECT_RATIOS:
            raise ValueError(f"unsupported media aspect ratio: {self.aspect_ratio}")
        if any(not str(subject).strip() for subject in self.subjects):
            raise ValueError("subjects must not contain empty values")

    def to_dict(self) -> dict[str, object]:
        return {
            "sceneDescription": self.scene_description,
            "subjects": list(self.subjects),
            "environment": self.environment,
            "action": self.action,
            "composition": self.composition,
            "moodLighting": self.mood_lighting,
            "style": self.style,
            "negativeConstraints": self.negative_constraints,
            "aspectRatio": self.aspect_ratio,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def to_prompt(self) -> str:
        sections = (
            ("Scene", self.scene_description),
            ("Subjects", ", ".join(self.subjects)),
            ("Environment", self.environment),
            ("Action", self.action),
            ("Composition", self.composition),
            ("Mood and lighting", self.mood_lighting),
            ("Style", self.style),
            ("Avoid", self.negative_constraints),
            ("Aspect ratio", self.aspect_ratio),
        )
        return "\n".join(f"{label}: {value}" for label, value in sections if value)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "VisualBrief":
        subjects_raw = raw.get("subjects", ())
        if not isinstance(subjects_raw, (list, tuple)):
            raise ValueError("subjects must be an array")
        return cls(
            scene_description=str(raw.get("sceneDescription", "")),
            subjects=tuple(str(value) for value in subjects_raw),
            environment=str(raw.get("environment", "")),
            action=str(raw.get("action", "")),
            composition=str(raw.get("composition", "")),
            mood_lighting=str(raw.get("moodLighting", "")),
            style=str(raw.get("style", "")),
            negative_constraints=str(raw.get("negativeConstraints", "")),
            aspect_ratio=str(raw.get("aspectRatio", "16:9")),
        )

    @classmethod
    def from_json(cls, raw: str) -> "VisualBrief":
        parsed: object = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("visual brief JSON must be an object")
        return cls.from_mapping(parsed)


@dataclass(frozen=True)
class MediaSourceSnapshot:
    session_id: str
    start_turn_id: int
    end_turn_id: int
    turns: tuple[models.MediaSourceTurn, ...]
    fingerprint: str
    snapshot_json: str


@dataclass(frozen=True)
class MediaBackgroundSourceSnapshot:
    session_id: str
    workspace_id: str
    story_id: int
    target_turn_id: int
    scene_attrs: Mapping[str, str]
    turns: tuple[models.MediaSourceTurn, ...]
    current_asset_id: str | None
    current_title: str
    last_decision: str
    last_reason: str
    fingerprint: str
    snapshot_json: str


class MediaBackgroundDecisionKind(StrEnum):
    KEEP = "keep"
    SWITCH = "switch"


MEDIA_BACKGROUND_DECISION_KEEP = MediaBackgroundDecisionKind.KEEP
MEDIA_BACKGROUND_DECISION_SWITCH = MediaBackgroundDecisionKind.SWITCH


@dataclass(frozen=True)
class MediaBackgroundDecision:
    decision: MediaBackgroundDecisionKind
    reason: str
    asset_id: str | None = None

    def __post_init__(self) -> None:
        try:
            decision = MediaBackgroundDecisionKind(self.decision)
        except ValueError as exc:
            raise ValueError(f"invalid media background decision: {self.decision}") from exc
        object.__setattr__(self, "decision", decision)
        if decision is MediaBackgroundDecisionKind.SWITCH and not self.asset_id:
            raise ValueError("switch background decision requires asset_id")


@dataclass(frozen=True)
class MediaSourceTurnView:
    turn_id: int
    roles: tuple[str, ...]
    preview: str
    message_count: int


@dataclass(frozen=True)
class VisualBriefResult:
    source: MediaSourceSnapshot
    brief: VisualBrief


@dataclass(frozen=True)
class MediaImageMetadata:
    title: str
    description: str
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        title = self.title.strip()
        description = self.description.strip()
        normalized_tags: list[str] = []
        seen: set[str] = set()
        for raw_tag in self.tags:
            tag = str(raw_tag).strip()
            normalized = tag.casefold()
            if not tag or normalized in seen:
                continue
            seen.add(normalized)
            normalized_tags.append(tag)
        if not title or len(title) > 200:
            raise ValueError("image metadata title must contain 1 to 200 characters")
        if not description or len(description) > 4000:
            raise ValueError("image metadata description must contain 1 to 4000 characters")
        if not 1 <= len(normalized_tags) <= 20:
            raise ValueError("image metadata must contain between 1 and 20 tags")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "tags", tuple(normalized_tags))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "MediaImageMetadata":
        tags = raw.get("tags", ())
        if not isinstance(tags, (list, tuple)):
            raise ValueError("image metadata tags must be an array")
        return cls(
            title=str(raw.get("title", "")),
            description=str(raw.get("description", "")),
            tags=tuple(str(tag) for tag in tags),
        )


@dataclass(frozen=True)
class MediaProviderDescriptor:
    key: str
    display_name: str
    kind: str
    available: bool
    reason: str = ""


@dataclass(frozen=True)
class MediaGenerationRequest:
    job_id: str
    session_id: str
    prompt: str
    visual_brief: VisualBrief
    generation_params: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    provider_asset_id: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class InspectedImage:
    data: bytes
    sha256: str
    canonical_ext: str
    mime_type: str
    byte_size: int


@dataclass(frozen=True)
class StoredImage:
    image: InspectedImage
    relative_path: str
    absolute_path: str
    file_created: bool


@dataclass(frozen=True)
class SessionGalleryAsset:
    bundle: models.SessionMediaAssetBundle
    source_stale: bool
    media_type: str = models.MEDIA_LIBRARY_TYPE_BACKGROUND


@dataclass(frozen=True)
class MediaBackgroundView:
    background: models.SessionMediaBackground | None
    asset: models.MediaDisplayAssetBundle | None
    source_mode: str
    manual_locked: bool
    revision_token: str
    state: models.SessionMediaBackgroundState


def mapping_json(raw: Mapping[str, object]) -> str:
    return json.dumps(
        dict(raw),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
