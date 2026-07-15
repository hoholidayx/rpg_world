"""Visual-brief planning contracts and the deterministic v1 demo planner."""

from __future__ import annotations

from typing import Protocol

from rpg_media.settings import DemoBriefSettings
from rpg_media.source import visible_excerpt
from rpg_media.types import MediaSourceSnapshot, VisualBrief


class VisualBriefPlanner(Protocol):
    def plan(self, source: MediaSourceSnapshot) -> VisualBrief: ...


class DemoVisualBriefPlanner:
    """Build an inspectable brief without invoking any text model."""

    def __init__(self, config: DemoBriefSettings | None = None) -> None:
        self._config = config or DemoBriefSettings()

    def plan(self, source: MediaSourceSnapshot) -> VisualBrief:
        contents = [
            message.content.strip()
            for turn in source.turns
            for message in turn.messages
            if message.content.strip()
        ]
        combined = " ".join(contents)
        scene_excerpt = visible_excerpt(combined, segment_length=120)
        action = visible_excerpt(contents[-1], segment_length=48) if contents else ""
        return VisualBrief(
            scene_description=(
                f"{self._config.scene_description_prefix}{scene_excerpt}"
            ).strip(),
            subjects=(),
            environment=self._config.environment,
            action=action,
            composition=self._config.composition,
            mood_lighting=self._config.mood_lighting,
            style=self._config.style,
            negative_constraints=self._config.negative_constraints,
            aspect_ratio=self._config.aspect_ratio,
        )
