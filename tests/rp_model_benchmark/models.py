"""Typed contracts for the story-neutral RP model benchmark."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DATASET_SCHEMA_VERSION = "rp-model-benchmark/1.0"


class BenchmarkCategory(StrEnum):
    FACT_GROUNDING = "fact_grounding"
    PLAYER_AGENCY = "player_agency"
    INFORMATION_ISOLATION = "information_isolation"
    INSTRUCTION_HIERARCHY = "instruction_hierarchy"
    OUTCOME_ADHERENCE = "outcome_adherence"
    MODE_BEHAVIOR = "mode_behavior"
    TOOL_FOLLOWING = "tool_following"
    NARRATIVE_QUALITY = "narrative_quality"


class BenchmarkToolName(StrEnum):
    OUTCOME = "rp_story_outcome"
    STATUS_VALUES = "status_table_set_values"
    STATUS_FIELDS = "status_table_edit_fields"


class CharacterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1)
    description: str = ""
    knows: list[str] = Field(default_factory=list)


class StatusRowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key: str = Field(min_length=1)
    value: str = ""
    runtime_key_locked: bool = Field(False, alias="runtimeKeyLocked")
    update_rule: str = Field("", alias="updateRule")
    metadata: dict[str, object] = Field(default_factory=dict)


class StatusTableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    table_id: int = Field(alias="tableId", ge=1)
    name: str = Field(min_length=1)
    description: str = ""
    rows: list[StatusRowSpec] = Field(default_factory=list)


class OutcomeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    outcome_code: Literal[
        "critical_success",
        "success",
        "success_with_cost",
        "setback",
        "critical_failure",
    ] = Field(alias="outcomeCode")
    label: str
    narrative_guidance: str = Field(alias="narrativeGuidance")
    reason: str
    actor: str = ""

    def tool_payload(self) -> dict[str, str]:
        return self.model_dump(by_alias=True)


class ToolExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    available: list[BenchmarkToolName] = Field(default_factory=list)
    required: list[BenchmarkToolName] = Field(default_factory=list)
    forbidden: list[BenchmarkToolName] = Field(default_factory=list)
    exact_sequence: list[BenchmarkToolName] | None = Field(
        None,
        alias="exactSequence",
    )
    argument_equals: dict[str, dict[str, object]] = Field(
        default_factory=dict,
        alias="argumentEquals",
    )
    outcome: OutcomeSpec | None = None

    @model_validator(mode="after")
    def validate_tools(self) -> "ToolExpectation":
        available = set(self.available)
        if not set(self.required).issubset(available):
            raise ValueError("required tools must be available")
        if set(self.required).intersection(self.forbidden):
            raise ValueError("a tool cannot be both required and forbidden")
        if self.exact_sequence is not None and not set(
            self.exact_sequence
        ).issubset(available):
            raise ValueError("exactSequence tools must be available")
        if BenchmarkToolName.OUTCOME in available and self.outcome is None:
            raise ValueError("outcome tool requires a fixed outcome payload")
        if self.outcome is not None and BenchmarkToolName.OUTCOME not in available:
            raise ValueError("outcome payload requires the outcome tool")
        return self


class TextExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    require_rp_xml: bool = Field(True, alias="requireRpXml")
    forbid_rp_xml: bool = Field(False, alias="forbidRpXml")
    required_literals: list[str] = Field(default_factory=list, alias="requiredLiterals")
    forbidden_literals: list[str] = Field(default_factory=list, alias="forbiddenLiterals")
    required_regex: list[str] = Field(default_factory=list, alias="requiredRegex")
    forbidden_regex: list[str] = Field(default_factory=list, alias="forbiddenRegex")
    forbid_internal_terms: bool = Field(True, alias="forbidInternalTerms")


class RPBenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    category: BenchmarkCategory
    smoke: bool = False
    mode: Literal["neutral", "ic", "ooc", "gm"] = "neutral"
    player_character: str = Field(alias="playerCharacter", min_length=1)
    scene: dict[str, str] = Field(default_factory=dict)
    characters: list[CharacterSpec] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    unknown_facts: list[str] = Field(default_factory=list, alias="unknownFacts")
    status_tables: list[StatusTableSpec] = Field(
        default_factory=list,
        alias="statusTables",
    )
    user_input: str = Field(alias="userInput", min_length=1)
    tools: ToolExpectation = Field(default_factory=ToolExpectation)
    text: TextExpectation = Field(default_factory=TextExpectation)
    semantic_rubric: list[str] = Field(alias="semanticRubric", min_length=1)

    @model_validator(mode="after")
    def validate_case(self) -> "RPBenchmarkCase":
        names = [item.name for item in self.characters]
        if self.player_character not in names:
            raise ValueError("playerCharacter must be present in characters")
        table_ids = [item.table_id for item in self.status_tables]
        if len(table_ids) != len(set(table_ids)):
            raise ValueError("status table ids must be unique within a case")
        if self.text.require_rp_xml and self.text.forbid_rp_xml:
            raise ValueError("RP XML cannot be both required and forbidden")
        if self.mode == "ooc" and self.text.require_rp_xml:
            raise ValueError("OOC cases must not require RP XML")
        return self


class RPBenchmarkDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal[DATASET_SCHEMA_VERSION] = Field(alias="schemaVersion")
    dataset_id: str = Field(alias="datasetId", min_length=1)
    title: str = Field(min_length=1)
    cases: list[RPBenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "RPBenchmarkDataset":
        ids = [item.id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark case ids must be unique")
        return self


__all__ = [
    "BenchmarkCategory",
    "BenchmarkToolName",
    "CharacterSpec",
    "DATASET_SCHEMA_VERSION",
    "OutcomeSpec",
    "RPBenchmarkCase",
    "RPBenchmarkDataset",
    "StatusRowSpec",
    "StatusTableSpec",
    "TextExpectation",
    "ToolExpectation",
]
