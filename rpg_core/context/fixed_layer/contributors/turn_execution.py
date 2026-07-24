"""Turn-scoped mode and narrative-style fixed-layer contributor."""

from __future__ import annotations

from rpg_core.context.fixed_layer.models import (
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)
from rpg_core.agent.turn.models import TurnExecutionSnapshot

NARRATIVE_STYLE_SECTION_ID = "narrative_style"
NARRATIVE_STYLE_SOURCE = "narrative_style"


class TurnExecutionFixedLayerContributor(FixedLayerContributor):
    name = "turn_execution"

    def __init__(self, snapshot: TurnExecutionSnapshot) -> None:
        self._snapshot = snapshot

    def get_fixed_contribution(self) -> FixedLayerContribution:
        sections: list[FixedLayerSection] = []
        if self._snapshot.narrative_style_prompt.strip():
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
