"""Typed sidecar and report contracts for Story acceptance runs."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ACCEPTANCE_SCHEMA_VERSION = "story-acceptance/1.0"
_SUITES = ("smoke", "full")
_PRODUCTION_TOOL_NAMES = (
    "plot_sandbox_read",
    "plot_event_mark_next",
    "status_table_set_values",
    "status_table_edit_fields",
    "select_status_targets",
    "rp_story_outcome",
    "scene_time",
    "scene_attr",
)
_TEST_INSTRUCTION_PATTERN = re.compile(
    r"(?:调用|使用|触发).{0,16}(?:工具|tool|function)|"
    r"(?:tool[_ -]?call|json\s*schema|复述工具名)",
    re.IGNORECASE,
)


class AcceptanceStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"
    NOT_APPLICABLE = "not_applicable"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class _Model(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class StoryPackIdentity(_Model):
    project_id: str = Field(alias="projectId")
    source_revision: str = Field(alias="sourceRevision")
    source_digest: str = Field(alias="sourceDigest", pattern=r"^[0-9a-f]{64}$")


class ContextExpectation(_Model):
    required_refs: list[str] = Field(default_factory=list, alias="requiredRefs")
    forbidden_refs: list[str] = Field(default_factory=list, alias="forbiddenRefs")
    require_story_prompt: bool = Field(default=False, alias="requireStoryPrompt")
    require_opening: bool = Field(default=False, alias="requireOpening")
    player_portrayal_excluded: bool = Field(
        default=False,
        alias="playerPortrayalExcluded",
    )
    player_portrayal_included: bool = Field(
        default=False,
        alias="playerPortrayalIncluded",
    )

    @model_validator(mode="after")
    def _portrayal_mode(self) -> "ContextExpectation":
        if self.player_portrayal_excluded and self.player_portrayal_included:
            raise ValueError(
                "player portrayal cannot be both required and forbidden"
            )
        return self


class StatusExpectation(_Model):
    table_ref: str = Field(alias="tableRef")
    operation: Literal[
        "changed",
        "unchanged",
        "created",
        "renamed",
        "deleted",
        "key_exists",
        "key_missing",
    ]
    key: str | None = None
    key_regex: str | None = Field(default=None, alias="keyRegex")
    from_key: str | None = Field(default=None, alias="fromKey")
    to_key: str | None = Field(default=None, alias="toKey")
    value: str | None = None
    value_contains: str | None = Field(default=None, alias="valueContains")
    runtime_key_locked: bool | None = Field(
        default=None,
        alias="runtimeKeyLocked",
    )
    update_rule_empty: bool | None = Field(default=None, alias="updateRuleEmpty")
    metadata_empty: bool | None = Field(default=None, alias="metadataEmpty")

    @model_validator(mode="after")
    def _valid_regex(self) -> "StatusExpectation":
        if self.key_regex:
            re.compile(self.key_regex)
        if self.operation == "renamed" and not (
            self.from_key and self.to_key
        ):
            raise ValueError("renamed status expectations require fromKey and toKey")
        return self


class PlotExpectation(_Model):
    pending: bool | None = None
    pending_event_ref: str | None = Field(default=None, alias="pendingEventRef")
    decision_event_ref: str | None = Field(default=None, alias="decisionEventRef")
    decision_pool_ref: str | None = Field(default=None, alias="decisionPoolRef")
    forbidden_decision_pool_ref: str | None = Field(
        default=None,
        alias="forbiddenDecisionPoolRef",
    )
    source_kind: Literal["outline", "pool"] | None = Field(
        default=None,
        alias="sourceKind",
    )
    selection_origin: Literal["scheduler", "manual"] | None = Field(
        default=None,
        alias="selectionOrigin",
    )
    decision_status: Literal["triggered", "deferred", "error"] | None = Field(
        default=None,
        alias="decisionStatus",
    )
    scene_opportunity: bool | None = Field(default=None, alias="sceneOpportunity")
    snapshot_title: str | None = Field(default=None, alias="snapshotTitle")
    snapshot_directive: str | None = Field(default=None, alias="snapshotDirective")
    original_event_unchanged: bool = Field(
        default=False,
        alias="originalEventUnchanged",
    )
    directive_runtime_only: bool = Field(
        default=False,
        alias="directiveRuntimeOnly",
    )
    pool_ref: str | None = Field(default=None, alias="poolRef")
    cooldown_remaining_minutes: int | None = Field(
        default=None,
        alias="cooldownRemainingMinutes",
        ge=0,
    )
    cooldown_reason_code: str | None = Field(
        default=None,
        alias="cooldownReasonCode",
    )
    selection_method: str | None = Field(default=None, alias="selectionMethod")
    configured_batch_size: int | None = Field(
        default=None,
        alias="configuredBatchSize",
        ge=1,
        le=5,
    )
    actual_batch_size: int | None = Field(
        default=None,
        alias="actualBatchSize",
        ge=1,
        le=5,
    )


class OutcomeExpectation(_Model):
    required: bool = True
    code: Literal[
        "critical_failure",
        "failure",
        "success_with_cost",
        "success",
        "critical_success",
    ] | None = None
    one_per_turn: bool = Field(default=True, alias="onePerTurn")


class PersistenceExpectation(_Model):
    committed: bool = True
    opening_count: int | None = Field(default=None, alias="openingCount", ge=0)
    original_input_only: bool = Field(default=True, alias="originalInputOnly")


class StoryAcceptanceStep(_Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    mode: Literal["neutral", "ic", "ooc", "gm"] = "neutral"
    input: str = Field(min_length=1)
    stream: bool = False
    required_tools: list[str] = Field(default_factory=list, alias="requiredTools")
    forbidden_tools: list[str] = Field(default_factory=list, alias="forbiddenTools")
    required_exposed_tools: list[str] = Field(
        default_factory=list,
        alias="requiredExposedTools",
    )
    forbidden_exposed_tools: list[str] = Field(
        default_factory=list,
        alias="forbiddenExposedTools",
    )
    context: ContextExpectation | None = None
    status: list[StatusExpectation] = Field(default_factory=list)
    plot: PlotExpectation | None = None
    additional_plot_checks: list[PlotExpectation] = Field(
        default_factory=list,
        alias="additionalPlotChecks",
    )
    outcome: OutcomeExpectation | None = None
    persistence: PersistenceExpectation | None = None
    semantic_rubric: list[str] = Field(default_factory=list, alias="semanticRubric")
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, alias="timeoutSeconds", ge=30, le=900)

    @model_validator(mode="after")
    def _natural_player_input(self) -> "StoryAcceptanceStep":
        lowered = self.input.casefold()
        named_tools = [name for name in _PRODUCTION_TOOL_NAMES if name in lowered]
        if named_tools:
            raise ValueError(
                "acceptance player input must express normal story intent, not "
                f"production tool names: {named_tools}"
            )
        if _TEST_INSTRUCTION_PATTERN.search(self.input):
            raise ValueError(
                "acceptance player input must not instruct the model to call a tool"
            )
        for label, required, forbidden in (
            ("tool calls", self.required_tools, self.forbidden_tools),
            (
                "tool exposure",
                self.required_exposed_tools,
                self.forbidden_exposed_tools,
            ),
        ):
            overlap = sorted(set(required).intersection(forbidden))
            if overlap:
                raise ValueError(
                    f"acceptance {label} cannot be both required and forbidden: "
                    f"{overlap}"
                )
        return self


class StoryAcceptanceFlow(_Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str
    kind: str = "turns"
    suites: list[Literal["smoke", "full"]] = Field(
        default_factory=lambda: ["full"]
    )
    session_id: str | None = Field(
        default=None,
        alias="sessionId",
        pattern=r"^[A-Za-z0-9_]+$",
    )
    require_fixed_layer_stability: bool = Field(
        default=True,
        alias="requireFixedLayerStability",
    )
    steps: list[StoryAcceptanceStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_steps(self) -> "StoryAcceptanceFlow":
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError(f"flow {self.id!r} contains duplicate step ids")
        if len(self.suites) != len(set(self.suites)):
            raise ValueError(f"flow {self.id!r} contains duplicate suites")
        return self

    def selected_for(self, suite: str) -> bool:
        if suite not in _SUITES:
            raise ValueError(f"unknown acceptance suite: {suite!r}")
        return suite == "full" or "smoke" in self.suites


class StoryAcceptanceProfile(_Model):
    schema_version: Literal[ACCEPTANCE_SCHEMA_VERSION] = Field(
        alias="schemaVersion"
    )
    pack: StoryPackIdentity
    player_character_ref: str = Field(alias="playerCharacterRef")
    opening_ref: str | None = Field(default=None, alias="openingRef")
    flows: list[StoryAcceptanceFlow]

    @model_validator(mode="after")
    def _unique_flows(self) -> "StoryAcceptanceProfile":
        ids = [flow.id for flow in self.flows]
        if len(ids) != len(set(ids)):
            raise ValueError("acceptance profile contains duplicate flow ids")
        if not self.flows:
            raise ValueError("acceptance profile must contain at least one flow")
        return self


def generic_profile(
    *,
    project_id: str,
    source_revision: str,
    source_digest: str,
    player_character_ref: str,
    opening_ref: str | None,
    has_plot: bool,
) -> StoryAcceptanceProfile:
    """Build the zero-sidecar smoke profile from portable Story Pack facts."""

    flows: list[StoryAcceptanceFlow] = [
        StoryAcceptanceFlow(
            id="generic_context",
            title="通用 Opening 与 Context 冒烟",
            kind="context",
            suites=["smoke", "full"],
            steps=[
                StoryAcceptanceStep(
                    id="observe_opening",
                    mode="ic",
                    input="我暂时不替任何人作决定，只观察眼前已经发生的情况。",
                    context=ContextExpectation(
                        require_story_prompt=True,
                        require_opening=opening_ref is not None,
                        player_portrayal_excluded=True,
                    ),
                    semantic_rubric=[
                        "回复应承接当前 Opening 和场景，而不是另起无关故事。",
                        "回复不得替玩家角色补写未声明的台词、决定、行动或心理。",
                    ],
                )
            ],
        )
    ]
    if has_plot:
        flows.append(
            StoryAcceptanceFlow(
                id="generic_plot_read",
                title="通用 OOC 沙盘读取",
                kind="plot_read",
                suites=["smoke", "full"],
                steps=[
                    StoryAcceptanceStep(
                        id="read_plot",
                        mode="ooc",
                        input=(
                            "先暂停剧情，请查看当前沙盘，按大纲与事件池概括"
                            "已经定义的剧情素材；不要推进世界。"
                        ),
                        required_tools=["plot_sandbox_read"],
                        forbidden_exposed_tools=[
                            "status_table_set_values",
                            "status_table_edit_fields",
                            "rp_story_outcome",
                        ],
                    )
                ],
            )
        )
    return StoryAcceptanceProfile(
        schema_version=ACCEPTANCE_SCHEMA_VERSION,
        pack=StoryPackIdentity(
            project_id=project_id,
            source_revision=source_revision,
            source_digest=source_digest,
        ),
        player_character_ref=player_character_ref,
        opening_ref=opening_ref,
        flows=flows,
    )


__all__ = [
    "ACCEPTANCE_SCHEMA_VERSION",
    "AcceptanceStatus",
    "ContextExpectation",
    "OutcomeExpectation",
    "PersistenceExpectation",
    "PlotExpectation",
    "StatusExpectation",
    "StoryAcceptanceFlow",
    "StoryAcceptanceProfile",
    "StoryAcceptanceStep",
    "StoryPackIdentity",
    "generic_profile",
]
