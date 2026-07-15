"""Framework-neutral media contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class MediaBackgroundView:
    background: models.SessionMediaBackground
    asset: SessionGalleryAsset


def mapping_json(raw: Mapping[str, object]) -> str:
    return json.dumps(
        dict(raw),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
