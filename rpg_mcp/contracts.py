"""Neutral contracts shared by the portable design store and RPG runtime adapter.

This module deliberately imports no ``rpg_core`` or ``rpg_data`` package so
``rpg-world-mcp --mode design`` remains usable without initializing the RPG
runtime.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CONTRACT_VERSION = "2.0"
STORY_DESIGN_SCHEMA_VERSION = "story-design/2.0"
STORY_PACK_SCHEMA_VERSION = "rpg-story-pack/2.0"
PROJECT_SCHEMA_VERSION = "story-design-project/2.0"
STORY_RUNTIME_METADATA_KEY = "_rpgStoryDesign"

CHARACTER_DETAIL_TAG_NPC_PORTRAYAL = "scope:npc_portrayal"
OBJECTIVE_CHARACTER_DETAIL_TAGS = frozenset({
    "kind:appearance",
    "kind:background",
    "kind:relationship",
    "kind:ability",
})
PORTRAYAL_CHARACTER_DETAIL_TAGS = frozenset({
    "kind:personality",
    "kind:speech",
    "kind:behavior",
    "kind:psychology",
})
RESERVED_CHARACTER_DETAIL_TAGS = frozenset({
    *OBJECTIVE_CHARACTER_DETAIL_TAGS,
    *PORTRAYAL_CHARACTER_DETAIL_TAGS,
    CHARACTER_DETAIL_TAG_NPC_PORTRAYAL,
})

RESOURCE_SECTIONS = (
    "story",
    "openings",
    "characters",
    "lorebook",
    "statusTables",
    "composer",
    "rpModules",
    "plotSchedule",
    "visualCatalog",
)

_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,127}$")
_SCENE_TIME_RE = re.compile(
    r"^\s*(?P<year>\d+)\s*年\s*"
    r"(?P<month>\d+)\s*月\s*"
    r"(?P<day>\d+)\s*日\s*"
    r"(?P<hour>\d+)\s*时"
    r"(?:\s*(?P<minute>\d+)\s*分)?\s*$"
)


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(item[:1].upper() + item[1:] for item in tail)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_stable_id(value: str, field_name: str = "stable id") -> str:
    normalized = str(value or "").strip()
    if not _STABLE_ID_RE.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must match {_STABLE_ID_RE.pattern!r}"
        )
    return normalized


def validate_scene_time(value: str) -> str:
    normalized = str(value or "").strip()
    match = _SCENE_TIME_RE.fullmatch(normalized)
    if match is None:
        raise ValueError("scene time must match 'Y 年 M 月 D 日 H 时 [M 分]'")
    parsed = {
        key: int(raw) if raw is not None else 0
        for key, raw in match.groupdict().items()
    }
    if parsed["year"] < 1:
        raise ValueError("scene time year must be at least 1")
    if not 1 <= parsed["month"] <= 12:
        raise ValueError("scene time month must be between 1 and 12")
    if not 1 <= parsed["day"] <= 31:
        raise ValueError("scene time day must be between 1 and 31")
    if not 0 <= parsed["hour"] <= 23:
        raise ValueError("scene time hour must be between 0 and 23")
    if not 0 <= parsed["minute"] <= 59:
        raise ValueError("scene time minute must be between 0 and 59")
    return normalized


def validate_story_text_template(value: str) -> str:
    template = str(value or "")
    index = 0
    while index < len(template):
        if template.startswith("{{", index):
            escaped_end = template.find("}}", index + 2)
            if escaped_end >= 0 and _is_template_identifier(
                template[index + 2:escaped_end]
            ):
                index = escaped_end + 2
                continue
        if template[index] == "{":
            token_end = template.find("}", index + 1)
            if token_end >= 0:
                variable = template[index + 1:token_end]
                if _is_template_identifier(variable):
                    if variable != "USER_PLAY_ROLE_NAME":
                        raise ValueError(
                            "unsupported Story template variable: "
                            f"{{{variable}}}"
                        )
                    index = token_end + 1
                    continue
        index += 1
    return template


class ProjectIdentity(ContractModel):
    project_id: str = "story-design"
    name: str = "未命名故事设计"
    language: str = "zh-CN"
    phase: Literal[
        "idea",
        "architecture",
        "resource_design",
        "package_ready",
        "runtime_synced",
    ] = "idea"

    @field_validator("project_id")
    @classmethod
    def _project_id(cls, value: str) -> str:
        return validate_stable_id(value, "projectId")


class RuntimeTarget(ContractModel):
    workspace_id: str = ""
    workspace_name: str = ""
    workspace_root: str = ""
    story_id: int | None = Field(default=None, gt=0)
    allow_create_workspace: bool = False

    @field_validator("workspace_id")
    @classmethod
    def _workspace_id(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if normalized and not _WORKSPACE_ID_RE.fullmatch(normalized):
            raise ValueError(
                f"workspaceId must match {_WORKSPACE_ID_RE.pattern!r}"
            )
        return normalized

    @field_validator("workspace_root")
    @classmethod
    def _workspace_root(cls, value: str) -> str:
        normalized = str(value or "").strip().replace("\\", "/")
        if not normalized:
            return ""
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("workspaceRoot must be a safe relative path")
        return path.as_posix()


class StoryCore(ContractModel):
    stable_id: str = "story"
    title: str = ""
    summary: str = ""
    story_prompt: str = ""
    time_setting: str = ""
    logline: str = ""
    themes: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("story_prompt")
    @classmethod
    def _story_prompt(cls, value: str) -> str:
        return validate_story_text_template(value)

    @field_validator("metadata")
    @classmethod
    def _metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if STORY_RUNTIME_METADATA_KEY in value:
            raise ValueError(
                f"story metadata key {STORY_RUNTIME_METADATA_KEY!r} is reserved"
            )
        return value


class OpeningSpec(ContractModel):
    stable_id: str
    title: str
    message: str
    sort_order: int = Field(default=0, ge=0)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _required_text(value, "opening title")

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        return validate_story_text_template(
            _required_text(value, "opening message")
        )


class CharacterDetailSpec(ContractModel):
    stable_id: str
    name: str
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            tag = str(raw or "").strip()
            if not tag or tag in seen:
                continue
            if (
                (tag.startswith("kind:") or tag.startswith("scope:"))
                and tag not in RESERVED_CHARACTER_DETAIL_TAGS
            ):
                raise ValueError(
                    f"unsupported reserved character detail tag: {tag}"
                )
            normalized.append(tag)
            seen.add(tag)
        if PORTRAYAL_CHARACTER_DETAIL_TAGS.intersection(seen):
            if CHARACTER_DETAIL_TAG_NPC_PORTRAYAL not in seen:
                normalized.append(CHARACTER_DETAIL_TAG_NPC_PORTRAYAL)
        return normalized


class CharacterSpec(ContractModel):
    stable_id: str
    name: str
    description: str = Field(
        default="",
        description=(
            "角色身份、经历与客观事实。不得写性格、说话方式、行为倾向或"
            "心理活动；这些演绎设定必须放入带内置 kind 标签的 details。"
        ),
    )
    aliases: list[str] = Field(default_factory=list)
    details: list[CharacterDetailSpec] = Field(default_factory=list)
    visual: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @model_validator(mode="after")
    def _unique_details(self) -> "CharacterSpec":
        _require_unique(self.details, "character detail")
        _require_unique_names(self.details, "character detail")
        return self


class LorebookSpec(ContractModel):
    stable_id: str
    name: str
    content: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    visual: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)


class StatusRowSpec(ContractModel):
    key: str
    value: str = ""
    runtime_key_locked: bool = False
    update_rule: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("update_rule")
    @classmethod
    def _update_rule(cls, value: str) -> str:
        return value.strip()


class StatusTableSpec(ContractModel):
    stable_id: str
    name: str
    status_kind: Literal["scene", "normal"] = "normal"
    character_ref: str | None = None
    description: str = ""
    rows: list[StatusRowSpec] = Field(default_factory=list)
    sort_order: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("character_ref")
    @classmethod
    def _character_ref(cls, value: str | None) -> str | None:
        return (
            validate_stable_id(value, "characterRef")
            if value is not None
            else None
        )

    @model_validator(mode="after")
    def _rows(self) -> "StatusTableSpec":
        keys = [row.key.strip() for row in self.rows]
        if any(not key for key in keys):
            raise ValueError("status row keys must not be empty")
        if len(keys) != len(set(keys)):
            raise ValueError("status row keys must be unique within a table")
        if self.status_kind == "scene":
            required = {"时间", "位置", "在场人物"}
            missing = sorted(required.difference(keys))
            if missing:
                raise ValueError(
                    "scene status table is missing fixed key(s): "
                    + ", ".join(missing)
                )
            time_row = next(row for row in self.rows if row.key == "时间")
            validate_scene_time(time_row.value)
        return self


class NarrativeStyleSpec(ContractModel):
    stable_id: str
    name: str
    prompt: str = ""
    is_base: bool = False
    sort_order: int = Field(default=0, ge=0)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)


class QuickReplySpec(ContractModel):
    stable_id: str
    title: str
    message: str
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("title", "message")
    @classmethod
    def _required_fields(cls, value: str, info: Any) -> str:
        return _required_text(value, f"quick reply {info.field_name}")


class RPModuleSpec(ContractModel):
    module_name: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("module_name")
    @classmethod
    def _module_name(cls, value: str) -> str:
        return validate_stable_id(value, "moduleName").lower()

    @model_validator(mode="after")
    def _module_contract(self) -> "RPModuleSpec":
        if self.module_name == "message_mode" and self.config:
            raise ValueError("message_mode config must be empty")
        return self


class PlotPoolSpec(ContractModel):
    stable_id: str
    name: str
    description: str = ""
    selection_mode: Literal["random", "sequential"] = "random"
    priority: int = 0
    cooldown_minutes: int = Field(default=0, ge=0)
    enabled: bool = True

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _required_text(value, "plot pool name")


class PlotEventSpec(ContractModel):
    stable_id: str
    pool_ref: str
    title: str
    directive: str
    description: str = ""
    suitability_hint: str = ""
    dispatch_mode: Literal["forced", "soft"] = "soft"
    scheduled_time: str | None = None
    deadline_time: str | None = None
    position: int = Field(default=0, ge=0)
    enabled: bool = True
    allow_repeat: bool = False
    repeat_cooldown_minutes: int = Field(default=0, ge=0)

    @field_validator("stable_id", "pool_ref")
    @classmethod
    def _ids(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("title", "directive")
    @classmethod
    def _required_fields(cls, value: str, info: Any) -> str:
        return _required_text(value, f"plot event {info.field_name}")

    @field_validator("scheduled_time", "deadline_time")
    @classmethod
    def _times(cls, value: str | None) -> str | None:
        return validate_scene_time(value) if value is not None else None

    @model_validator(mode="after")
    def _window_and_repeat(self) -> "PlotEventSpec":
        if self.allow_repeat and self.repeat_cooldown_minutes <= 0:
            raise ValueError("repeating events require a positive cooldown")
        if not self.allow_repeat and self.repeat_cooldown_minutes:
            raise ValueError("non-repeating events must use a zero cooldown")
        if (
            self.scheduled_time is not None
            and self.deadline_time is not None
            and _scene_ordinal(self.deadline_time)
            <= _scene_ordinal(self.scheduled_time)
        ):
            raise ValueError("deadlineTime must be later than scheduledTime")
        return self


class PlotNodeSpec(ContractModel):
    stable_id: str
    event_ref: str
    scheduled_time: str
    dispatch_mode: Literal["forced", "soft"] = "soft"
    position: int = Field(default=0, ge=0)
    enabled: bool = True

    @field_validator("stable_id", "event_ref")
    @classmethod
    def _ids(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("scheduled_time")
    @classmethod
    def _time(cls, value: str) -> str:
        return validate_scene_time(value)


class PlotOutlineSpec(ContractModel):
    stable_id: str
    name: str
    description: str = ""
    priority: int = 0
    enabled: bool = True
    nodes: list[PlotNodeSpec] = Field(default_factory=list)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _required_text(value, "plot outline name")

    @model_validator(mode="after")
    def _nodes(self) -> "PlotOutlineSpec":
        _require_unique(self.nodes, "plot node")
        ordered = sorted(self.nodes, key=lambda item: item.position)
        ordinals = [_scene_ordinal(item.scheduled_time) for item in ordered]
        if ordinals != sorted(ordinals):
            raise ValueError(
                "outline node times must be nondecreasing in position order"
            )
        return self


class PlotScheduleSpec(ContractModel):
    pools: list[PlotPoolSpec] = Field(default_factory=list)
    events: list[PlotEventSpec] = Field(default_factory=list)
    outlines: list[PlotOutlineSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _references(self) -> "PlotScheduleSpec":
        _require_unique(self.pools, "plot pool")
        _require_unique(self.events, "plot event")
        _require_unique(self.outlines, "plot outline")
        pool_ids = {item.stable_id for item in self.pools}
        event_ids = {item.stable_id for item in self.events}
        for event in self.events:
            if event.pool_ref not in pool_ids:
                raise ValueError(
                    f"plot event {event.stable_id} references unknown pool "
                    f"{event.pool_ref}"
                )
        for outline in self.outlines:
            for node in outline.nodes:
                if node.event_ref not in event_ids:
                    raise ValueError(
                        f"plot node {node.stable_id} references unknown event "
                        f"{node.event_ref}"
                    )
        return self


class VisualSpec(ContractModel):
    stable_id: str
    asset_type: Literal[
        "character_portrait",
        "character_sprite",
        "scene",
        "location",
        "object",
        "map",
        "costume",
        "other",
    ]
    title: str
    prompt: str
    negative_prompt: str = ""
    subject_refs: list[str] = Field(default_factory=list)
    visual_anchors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stable_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        return validate_stable_id(value)

    @field_validator("title", "prompt")
    @classmethod
    def _required_fields(cls, value: str, info: Any) -> str:
        return _required_text(value, f"visual specification {info.field_name}")


class StoryResources(ContractModel):
    openings: list[OpeningSpec] = Field(default_factory=list, max_length=3)
    characters: list[CharacterSpec] = Field(default_factory=list)
    lorebook: list[LorebookSpec] = Field(default_factory=list)
    status_tables: list[StatusTableSpec] = Field(default_factory=list)
    narrative_styles: list[NarrativeStyleSpec] = Field(default_factory=list)
    quick_replies: list[QuickReplySpec] = Field(default_factory=list)
    rp_modules: list[RPModuleSpec] = Field(default_factory=list)
    plot_schedule: PlotScheduleSpec = Field(default_factory=PlotScheduleSpec)
    visual_catalog: list[VisualSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_and_owned(self) -> "StoryResources":
        for values, label in (
            (self.openings, "opening"),
            (self.characters, "character"),
            (self.lorebook, "lorebook entry"),
            (self.status_tables, "status table"),
            (self.narrative_styles, "narrative style"),
            (self.quick_replies, "quick reply"),
            (self.visual_catalog, "visual specification"),
        ):
            _require_unique(values, label)
        for values, label, name_field in (
            (self.openings, "opening", "title"),
            (self.characters, "character", "name"),
            (self.lorebook, "lorebook entry", "name"),
            (self.status_tables, "status table", "name"),
            (self.narrative_styles, "narrative style", "name"),
            (self.quick_replies, "quick reply", "title"),
        ):
            _require_unique_names(values, label, name_field=name_field)
        module_names = [item.module_name for item in self.rp_modules]
        if len(module_names) != len(set(module_names)):
            raise ValueError("RP module names must be unique")
        _require_unique(
            [
                detail
                for character in self.characters
                for detail in character.details
            ],
            "character detail",
        )
        _require_unique(
            [
                node
                for outline in self.plot_schedule.outlines
                for node in outline.nodes
            ],
            "plot node",
        )
        if sum(item.is_base for item in self.narrative_styles) > 1:
            raise ValueError("at most one narrative style may be marked isBase")
        return self


class DecisionRecord(ContractModel):
    id: str
    topic: str
    decision: str
    rationale: str = ""
    status: Literal["confirmed", "tentative", "superseded"] = "confirmed"
    decided_at: str = Field(default_factory=utc_now)

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_stable_id(value, "decision id")


class OpenQuestion(ContractModel):
    id: str
    question: str
    options: list[str] = Field(default_factory=list)
    context: str = ""
    status: Literal["open", "resolved", "deferred"] = "open"

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_stable_id(value, "question id")


class SourceRecord(ContractModel):
    id: str
    title: str
    source_type: str = ""
    locator: str = ""
    notes: str = ""

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        return validate_stable_id(value, "source id")

    @field_validator("locator")
    @classmethod
    def _locator(cls, value: str) -> str:
        normalized = str(value or "").strip().replace("\\", "/")
        if not normalized:
            return ""
        lowered = normalized.lower()
        path = PurePosixPath(normalized)
        if (
            lowered.startswith("file:")
            or path.is_absolute()
            or re.match(r"^[A-Za-z]:/", normalized)
            or (
                "://" not in normalized
                and ".." in path.parts
            )
        ):
            raise ValueError(
                "source locator must be an external URL/id or safe "
                "DesignProject-relative path"
            )
        return normalized


class StoryDesignDocument(ContractModel):
    schema_version: Literal[STORY_DESIGN_SCHEMA_VERSION] = (
        STORY_DESIGN_SCHEMA_VERSION
    )
    project: ProjectIdentity = Field(default_factory=ProjectIdentity)
    target: RuntimeTarget = Field(default_factory=RuntimeTarget)
    story: StoryCore = Field(default_factory=StoryCore)
    resources: StoryResources = Field(default_factory=StoryResources)
    decisions: list[DecisionRecord] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _records(self) -> "StoryDesignDocument":
        _require_unique(self.decisions, "decision", id_field="id")
        _require_unique(self.open_questions, "open question", id_field="id")
        _require_unique(self.sources, "source", id_field="id")
        _require_status_character_refs(self.resources)
        return self


class StoryPackApplyPolicy(ContractModel):
    mode: Literal["merge"] = "merge"
    delete_missing: Literal[False] = False


class StoryPack(ContractModel):
    schema_version: Literal[STORY_PACK_SCHEMA_VERSION] = STORY_PACK_SCHEMA_VERSION
    contract_version: Literal[CONTRACT_VERSION] = CONTRACT_VERSION
    pack_id: str
    project_id: str
    story_stable_id: str
    source_revision: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: str
    target: RuntimeTarget
    included_sections: list[
        Literal[
            "story",
            "openings",
            "characters",
            "lorebook",
            "statusTables",
            "composer",
            "rpModules",
            "plotSchedule",
            "visualCatalog",
        ]
    ]
    story: StoryCore
    resources: StoryResources = Field(default_factory=StoryResources)
    apply_policy: StoryPackApplyPolicy = Field(
        default_factory=StoryPackApplyPolicy
    )

    @field_validator("pack_id", "project_id", "story_stable_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return validate_stable_id(value)

    @model_validator(mode="after")
    def _ready_for_runtime(self) -> "StoryPack":
        if not self.target.workspace_id:
            raise ValueError("target.workspaceId is required")
        if not self.story.title.strip():
            raise ValueError("story.title is required")
        if self.story_stable_id != self.story.stable_id:
            raise ValueError("storyStableId must equal story.stableId")
        if not self.included_sections:
            raise ValueError("includedSections must not be empty")
        if len(self.included_sections) != len(set(self.included_sections)):
            raise ValueError("includedSections must not contain duplicates")
        _require_omitted_sections_empty(
            self.resources,
            included_sections=set(self.included_sections),
        )
        if (
            "statusTables" in self.included_sections
            and "characters" in self.included_sections
        ):
            _require_status_character_refs(self.resources)
        if self.target.allow_create_workspace:
            if not self.target.workspace_name.strip():
                raise ValueError(
                    "target.workspaceName is required when workspace creation "
                    "is allowed"
                )
            if not self.target.workspace_root:
                raise ValueError(
                    "target.workspaceRoot is required when workspace creation "
                    "is allowed"
                )
        return self


def build_story_pack(
    document: StoryDesignDocument,
    *,
    source_revision: str,
    source_digest: str,
    included_sections: list[str] | tuple[str, ...] | None = None,
    target_overrides: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> StoryPack:
    sections = list(included_sections or RESOURCE_SECTIONS)
    unexpected = sorted(set(sections).difference(RESOURCE_SECTIONS))
    if unexpected:
        raise ValueError(f"unknown Story Pack section(s): {unexpected}")
    if len(sections) != len(set(sections)):
        raise ValueError("Story Pack sections must be unique")

    target_values = document.target.model_dump(by_alias=True)
    target_values.update(target_overrides or {})
    target = RuntimeTarget.model_validate(target_values)
    raw_resources = document.resources.model_dump(by_alias=True)
    section_fields = {
        "openings": "openings",
        "characters": "characters",
        "lorebook": "lorebook",
        "statusTables": "statusTables",
        "composer": ("narrativeStyles", "quickReplies"),
        "rpModules": "rpModules",
        "plotSchedule": "plotSchedule",
        "visualCatalog": "visualCatalog",
    }
    selected_resources: dict[str, Any] = {}
    for section, fields in section_fields.items():
        if section not in sections:
            continue
        for field in (fields if isinstance(fields, tuple) else (fields,)):
            selected_resources[field] = raw_resources[field]

    scope_digest = digest_json({
        "includedSections": sections,
        "target": target.model_dump(by_alias=True),
    })[:12]
    project_prefix = document.project.project_id[:88].rstrip(".-")
    pack_id = validate_stable_id(
        f"{project_prefix}-{source_revision}-{scope_digest}",
        "packId",
    )
    return StoryPack.model_validate({
        "schemaVersion": STORY_PACK_SCHEMA_VERSION,
        "contractVersion": CONTRACT_VERSION,
        "packId": pack_id,
        "projectId": document.project.project_id,
        "storyStableId": document.story.stable_id,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "generatedAt": generated_at or utc_now(),
        "target": target.model_dump(by_alias=True),
        "includedSections": sections,
        "story": document.story.model_dump(by_alias=True),
        "resources": selected_resources,
        "applyPolicy": {"mode": "merge", "deleteMissing": False},
    })


def _require_unique(
    values: list[Any],
    label: str,
    *,
    id_field: str = "stable_id",
) -> None:
    ids = [getattr(item, id_field) for item in values]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} ids must be unique")


def _require_unique_names(
    values: list[Any],
    label: str,
    *,
    name_field: str = "name",
) -> None:
    names = [str(getattr(item, name_field)).strip() for item in values]
    if any(not name for name in names):
        raise ValueError(f"{label} names must not be empty")
    if len(names) != len(set(names)):
        raise ValueError(f"{label} names must be unique")


def _required_text(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized


def _is_template_identifier(value: str) -> bool:
    if not value or not ("A" <= value[0] <= "Z"):
        return False
    return all(
        character == "_"
        or "0" <= character <= "9"
        or "A" <= character <= "Z"
        for character in value
    )


def _require_status_character_refs(resources: StoryResources) -> None:
    character_ids = {item.stable_id for item in resources.characters}
    for table in resources.status_tables:
        if (
            table.character_ref is not None
            and table.character_ref not in character_ids
        ):
            raise ValueError(
                f"status table {table.stable_id} references unknown "
                f"character {table.character_ref}"
            )


def _require_omitted_sections_empty(
    resources: StoryResources,
    *,
    included_sections: set[str],
) -> None:
    section_values = {
        "openings": resources.openings,
        "characters": resources.characters,
        "lorebook": resources.lorebook,
        "statusTables": resources.status_tables,
        "composer": (
            *resources.narrative_styles,
            *resources.quick_replies,
        ),
        "rpModules": resources.rp_modules,
        "plotSchedule": (
            *resources.plot_schedule.pools,
            *resources.plot_schedule.events,
            *resources.plot_schedule.outlines,
        ),
        "visualCatalog": resources.visual_catalog,
    }
    populated_omissions = sorted(
        section
        for section, values in section_values.items()
        if section not in included_sections and values
    )
    if populated_omissions:
        raise ValueError(
            "resources for omitted Story Pack section(s) must be empty: "
            + ", ".join(populated_omissions)
        )


def _scene_ordinal(value: str) -> int:
    match = _SCENE_TIME_RE.fullmatch(validate_scene_time(value))
    assert match is not None
    values = {
        key: int(raw) if raw is not None else 0
        for key, raw in match.groupdict().items()
    }
    days = (
        ((values["year"] - 1) * 12 + (values["month"] - 1)) * 31
        + values["day"]
        - 1
    )
    return ((days * 24) + values["hour"]) * 60 + values["minute"]


__all__ = [
    "CHARACTER_DETAIL_TAG_NPC_PORTRAYAL",
    "CONTRACT_VERSION",
    "OBJECTIVE_CHARACTER_DETAIL_TAGS",
    "PORTRAYAL_CHARACTER_DETAIL_TAGS",
    "PROJECT_SCHEMA_VERSION",
    "RESERVED_CHARACTER_DETAIL_TAGS",
    "RESOURCE_SECTIONS",
    "STORY_DESIGN_SCHEMA_VERSION",
    "STORY_PACK_SCHEMA_VERSION",
    "STORY_RUNTIME_METADATA_KEY",
    "RuntimeTarget",
    "StoryDesignDocument",
    "StoryPack",
    "build_story_pack",
    "canonical_json",
    "digest_json",
    "utc_now",
    "validate_scene_time",
    "validate_story_text_template",
]
