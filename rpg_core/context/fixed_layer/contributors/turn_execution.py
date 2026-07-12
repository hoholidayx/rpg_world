"""Turn-scoped mode and narrative-style fixed-layer contributor."""

from __future__ import annotations

from rpg_core.context.fixed_layer.models import (
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)
from rpg_core.turns import TurnExecutionSnapshot, TurnMode

TURN_MODE_SECTION_ID = "turn_mode"
TURN_MODE_SOURCE = "turn_mode"
NARRATIVE_STYLE_SECTION_ID = "narrative_style"
NARRATIVE_STYLE_SOURCE = "narrative_style"


class TurnExecutionFixedLayerContributor(FixedLayerContributor):
    name = "turn_execution"

    def __init__(self, snapshot: TurnExecutionSnapshot) -> None:
        self._snapshot = snapshot

    def get_fixed_contribution(self) -> FixedLayerContribution:
        sections: list[FixedLayerSection] = []
        mode_prompt = self._snapshot.mode_prompt.strip()
        if self._snapshot.request.mode is TurnMode.OOC:
            hard_boundary = (
                "硬性边界：本轮是场外讨论。不得推进故事时间线，不得作剧情裁定，"
                "不得新增或修改场景、角色或状态事实；直接使用普通文本回答，"
                "无需使用 RP 正文标签。"
            )
            mode_prompt = f"{hard_boundary}\n{mode_prompt}" if mode_prompt else hard_boundary
        if mode_prompt:
            sections.append(FixedLayerSection(
                id=TURN_MODE_SECTION_ID,
                title=f"本轮模式：{self._snapshot.request.mode.value.upper()}",
                content=mode_prompt,
                priority=5,
                source=TURN_MODE_SOURCE,
                source_kind=TURN_MODE_SOURCE,
                item_count=1,
            ))
        if (
            self._snapshot.policy.apply_narrative_style
            and self._snapshot.narrative_style_prompt.strip()
        ):
            sections.append(FixedLayerSection(
                id=NARRATIVE_STYLE_SECTION_ID,
                title=f"叙事风格：{self._snapshot.narrative_style_name}",
                content=self._snapshot.narrative_style_prompt.strip(),
                priority=15,
                source=NARRATIVE_STYLE_SOURCE,
                source_kind=NARRATIVE_STYLE_SOURCE,
                item_count=1,
            ))
        return FixedLayerContribution(sections=sections)
