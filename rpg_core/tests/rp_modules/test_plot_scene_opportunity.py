from __future__ import annotations

from dataclasses import dataclass

from rpg_core.rp_modules.plot_scheduler.scene_opportunity import (
    PlotSceneOpportunityCommitService,
    PlotSceneOpportunityTurnState,
)
from rpg_data import models


@dataclass
class _Data:
    replaced: list[tuple[str, int | None, int]]
    cleared: list[tuple[str, int | None]]

    def replace_scene_opportunity(
        self,
        session_id: str,
        *,
        expected_version: int | None,
        source_turn_id: int,
    ) -> models.SessionPlotSceneOpportunity:
        self.replaced.append(
            (session_id, expected_version, source_turn_id)
        )
        return models.SessionPlotSceneOpportunity(
            session_id=session_id,
            source_turn_id=source_turn_id,
            version=(expected_version or 0) + 1,
        )

    def clear_scene_opportunity(
        self,
        session_id: str,
        *,
        expected_version: int | None = None,
    ) -> int:
        self.cleared.append((session_id, expected_version))
        return 1


def test_scene_opportunity_state_ignores_unchanged_scene_without_base() -> None:
    state = PlotSceneOpportunityTurnState()

    state.finalize(source_turn_id=1, scene_changed=False)

    assert state.available is False
    assert state.dirty is False
    assert state.desired_source_turn_id is None


def test_scene_opportunity_state_consumes_or_replaces_the_base() -> None:
    base = models.SessionPlotSceneOpportunity(
        session_id="s1",
        source_turn_id=1,
        version=4,
    )
    consumed = PlotSceneOpportunityTurnState(base=base)
    consumed.consume()
    consumed.finalize(source_turn_id=2, scene_changed=False)
    assert consumed.dirty is True
    assert consumed.desired_source_turn_id is None

    replaced = PlotSceneOpportunityTurnState(base=base)
    replaced.consume()
    replaced.finalize(source_turn_id=2, scene_changed=True)
    assert replaced.dirty is True
    assert replaced.desired_source_turn_id == 2


def test_scene_opportunity_commit_uses_base_version_for_clear_and_replace() -> None:
    data = _Data(replaced=[], cleared=[])
    service = PlotSceneOpportunityCommitService(data)
    base = models.SessionPlotSceneOpportunity(
        session_id="s1",
        source_turn_id=1,
        version=4,
    )

    clear_state = PlotSceneOpportunityTurnState(base=base)
    clear_state.consume()
    clear_state.finalize(source_turn_id=2, scene_changed=False)
    service.commit("s1", clear_state)

    replace_state = PlotSceneOpportunityTurnState(base=base)
    replace_state.consume()
    replace_state.finalize(source_turn_id=2, scene_changed=True)
    service.commit("s1", replace_state)

    create_state = PlotSceneOpportunityTurnState()
    create_state.finalize(source_turn_id=3, scene_changed=True)
    service.commit("s1", create_state)

    assert data.cleared == [("s1", 4)]
    assert data.replaced == [
        ("s1", 4, 2),
        ("s1", None, 3),
    ]
