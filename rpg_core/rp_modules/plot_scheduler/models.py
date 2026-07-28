"""Immutable turn-local contracts for plot scheduling."""

from __future__ import annotations

import json
from dataclasses import dataclass

from commons.scene_time import SceneTime
from rpg_data import models as data_models

PLOT_SUITABILITY_REASON_MAX_CHARS = 500


@dataclass(frozen=True)
class PlotScheduleInjection:
    source_kind: str
    source_id: int
    event_id: int
    container_id: int
    container_name: str
    event_title: str
    directive: str
    dispatch_mode: str
    scene_time: SceneTime | None
    reason: str = ""


@dataclass(frozen=True)
class PlotScheduleCandidate:
    """One due definition selected for a turn-local scheduling lane."""

    source_kind: str
    source_id: int
    event: data_models.StoryPlotEvent
    container_id: int
    container_name: str
    dispatch_mode: str
    scheduled_time: SceneTime | None
    priority: int


@dataclass(frozen=True)
class PlotSuitabilityDecision:
    suitable: bool
    reason: str


@dataclass(frozen=True)
class PlotScheduleSnapshot:
    session_id: str
    story_id: int
    enabled: bool
    story: data_models.StoryPlotSchedule
    overrides: data_models.SessionPlotOverrides
    decisions: tuple[data_models.SessionPlotScheduleDecision, ...]
    pending_injection: data_models.SessionPlotPendingInjection | None = None
    scene_opportunity: data_models.SessionPlotSceneOpportunity | None = None
    judge_history_turns: int = 5
    soft_retry_intervening_turns: int = 1

    @classmethod
    def disabled(cls, session_id: str, story_id: int = 0) -> "PlotScheduleSnapshot":
        return cls(
            session_id=session_id,
            story_id=story_id,
            enabled=False,
            story=data_models.StoryPlotSchedule(story_id=story_id),
            overrides=data_models.SessionPlotOverrides(session_id=session_id),
            decisions=(),
            pending_injection=None,
            scene_opportunity=None,
        )

    @property
    def context_gate_reserve_text(self) -> str:
        candidate_directives = (
            [event.directive for event in self.story.events]
            if self.scene_opportunity is not None
            else []
        )
        candidate_titles = (
            [event.title for event in self.story.events]
            if self.scene_opportunity is not None
            else []
        )
        if self.pending_injection is not None:
            candidate_directives.append(self.pending_injection.directive)
            candidate_titles.append(self.pending_injection.event_title)
        directives = sorted(
            candidate_directives,
            key=_json_encoded_size,
            reverse=True,
        )
        if not directives:
            return ""
        slot_count = min(2, len(candidate_directives))
        event_titles = sorted(
            candidate_titles,
            key=_json_encoded_size,
            reverse=True,
        )
        container_names = sorted(
            (
                *(pool.name for pool in self.story.pools),
                *(outline.name for outline in self.story.outlines),
            ),
            key=_json_encoded_size,
            reverse=True,
        )
        return json.dumps(
            {
                "directives": directives[:slot_count],
                "eventTitles": event_titles[:slot_count],
                "containerNames": container_names[:slot_count],
                "suitabilityReasons": [
                    "元" * PLOT_SUITABILITY_REASON_MAX_CHARS
                    for _ in range(slot_count)
                ],
                "metadataReserve": "元" * (256 * slot_count),
            },
            ensure_ascii=False,
        )


def _json_encoded_size(value: str) -> int:
    return len(json.dumps(value, ensure_ascii=False))
