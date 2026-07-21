"""High-level tool and weighted selector for narrative outcomes."""

from __future__ import annotations

import json
import random

from rpg_core.tooling.base import BaseTool
from rpg_core.rp_modules.narrative_outcome.models import (
    NARRATIVE_OUTCOME_DEFINITIONS,
    NarrativeOutcomeSelection,
    StagedNarrativeOutcome,
)
from rpg_data.model.narrative_outcome import NarrativeOutcomeWeights


NARRATIVE_OUTCOME_TOOL_NAME = "rp_story_outcome"


class NarrativeOutcomeSampler:
    """Select one of five outcomes from an injectable 1..100 RNG."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def select(
        self,
        *,
        reason: str,
        actor: str,
        selection: NarrativeOutcomeSelection,
    ) -> StagedNarrativeOutcome:
        sample_value = int(self._rng.randint(1, 100))
        definition = self.definition_for_sample(
            sample_value,
            selection.effective_weights,
        )
        return StagedNarrativeOutcome(
            outcome_code=definition.code,
            label=definition.label,
            narrative_guidance=definition.narrative_guidance,
            reason=reason.strip(),
            actor=actor.strip(),
            sample_value=sample_value,
            effective_weights=selection.effective_weights,
            effective_source=selection.effective_source,
        )

    @staticmethod
    def definition_for_sample(
        sample_value: int,
        weights: NarrativeOutcomeWeights,
    ):
        if not 1 <= int(sample_value) <= 100:
            raise ValueError("sample_value must be within [1, 100]")

        cumulative = 0
        for definition, weight in zip(
            NARRATIVE_OUTCOME_DEFINITIONS,
            weights.values(),
            strict=True,
        ):
            cumulative += weight
            if sample_value <= cumulative:
                return definition
        raise RuntimeError("narrative outcome weights did not cover sample_value")


class NarrativeOutcomeTool(BaseTool):
    name = NARRATIVE_OUTCOME_TOOL_NAME
    description = (
        "裁定一个存在外部实质变数、且不同结果会改变剧情走向的行动或场景决策。"
        "只提供裁定原因和可选行动者；工具内部处理全部随机细节，并返回唯一且必须遵循的五级剧情结果。"
        "同一 turn 重复调用只会返回第一次结果。"
    )

    def __init__(self, module) -> None:
        self._module = module

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "需要裁定的单一外部变数，简洁说明行动、阻力或尚未确定的场景反应；"
                        "不要预写成功或失败。"
                    ),
                },
                "actor": {
                    "type": "string",
                    "description": "可选：发起行动或直接承受结果的角色/对象。",
                },
            },
            "required": ["reason"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: object) -> str:
        reason = str(kwargs.get("reason", "") or "").strip()
        if not reason:
            raise ValueError("reason must not be empty")
        staged = self._module.adjudicate(
            reason=reason,
            actor=str(kwargs.get("actor", "") or ""),
        )
        return json.dumps(
            staged.to_tool_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
