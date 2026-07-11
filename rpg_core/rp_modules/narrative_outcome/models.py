"""Typed narrative outcome definitions and staged decisions."""

from __future__ import annotations

from dataclasses import dataclass

from rpg_data.models import NarrativeOutcomeWeights


@dataclass(frozen=True)
class NarrativeOutcomeDefinition:
    code: str
    label: str
    narrative_guidance: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "label": self.label,
            "narrativeGuidance": self.narrative_guidance,
        }


NARRATIVE_OUTCOME_DEFINITIONS = (
    NarrativeOutcomeDefinition(
        code="critical_success",
        label="大成功",
        narrative_guidance=(
            "完整且超额达成 reason 描述的整体目标，并获得一个额外机会、信息或优势。"
        ),
    ),
    NarrativeOutcomeDefinition(
        code="success",
        label="成功",
        narrative_guidance="完整达成 reason 描述的整体目标，不附加重大代价。",
    ),
    NarrativeOutcomeDefinition(
        code="success_with_cost",
        label="成功但有代价",
        narrative_guidance=(
            "完整达成 reason 描述的整体目标，同时引入一个与行动相称的代价或复杂化；"
            "不得只完成子步骤，代价不得抵消整体目标已经达成。"
        ),
    ),
    NarrativeOutcomeDefinition(
        code="setback",
        label="失败但推进",
        narrative_guidance=(
            "未达成 reason 描述的整体目标，但必须提供新信息、替代路径或明确的下一步行动。"
        ),
    ),
    NarrativeOutcomeDefinition(
        code="critical_failure",
        label="重大失败",
        narrative_guidance=(
            "未达成 reason 描述的整体目标，并引入严重后果，但不得自动死亡、"
            "硬停剧情或永久剥夺玩家角色主权。"
        ),
    ),
)

NARRATIVE_OUTCOME_DEFINITION_BY_CODE = {
    definition.code: definition for definition in NARRATIVE_OUTCOME_DEFINITIONS
}


@dataclass(frozen=True)
class StagedNarrativeOutcome:
    outcome_code: str
    label: str
    narrative_guidance: str
    reason: str
    actor: str
    sample_value: int
    effective_weights: NarrativeOutcomeWeights
    effective_source: str

    def to_tool_payload(self) -> dict[str, str]:
        payload = {
            "outcomeCode": self.outcome_code,
            "label": self.label,
            "narrativeGuidance": self.narrative_guidance,
            "reason": self.reason,
        }
        if self.actor:
            payload["actor"] = self.actor
        return payload
