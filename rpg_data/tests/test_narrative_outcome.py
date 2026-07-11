from __future__ import annotations

import pytest
from peewee import IntegrityError

from rpg_data import models
from rpg_data.services import get_data_service_gateway


DEFAULT_WEIGHTS = models.NarrativeOutcomeWeights()
STORY_WEIGHTS = models.NarrativeOutcomeWeights(
    critical_success=10,
    success=30,
    success_with_cost=30,
    setback=25,
    critical_failure=5,
)
SESSION_WEIGHTS = models.NarrativeOutcomeWeights(
    critical_success=0,
    success=20,
    success_with_cost=50,
    setback=25,
    critical_failure=5,
)


def test_weights_validate_integer_range_and_exact_total() -> None:
    assert DEFAULT_WEIGHTS.to_dict() == {
        "critical_success": 5,
        "success": 25,
        "success_with_cost": 40,
        "setback": 25,
        "critical_failure": 5,
    }

    with pytest.raises(ValueError, match="integers"):
        models.NarrativeOutcomeWeights(critical_success=True)
    with pytest.raises(ValueError, match=r"within \[0, 100\]"):
        models.NarrativeOutcomeWeights(critical_success=-1, success=31)
    with pytest.raises(ValueError, match="sum to 100"):
        models.NarrativeOutcomeWeights(success=24)
    with pytest.raises(ValueError, match="must be an integer"):
        models.NarrativeOutcomeWeights.from_mapping({
            "critical_success": 5,
            "success": 25,
            "success_with_cost": 40,
            "setback": 25,
            "critical_failure": 5.0,
        })


def test_story_and_session_override_precedence_and_clear(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "narrative-selection.sqlite3")
    service = gateway.narrative_outcomes

    base = service.get_session_selection("s_forest001", DEFAULT_WEIGHTS)
    assert base is not None
    assert base.effective_weights == DEFAULT_WEIGHTS
    assert base.effective_source == models.NARRATIVE_OUTCOME_SOURCE_CONFIG

    story = gateway.catalog.get_session_story("s_forest001")
    assert story is not None
    story_selection = service.set_story_weights(
        story.workspace_id,
        story.id,
        STORY_WEIGHTS,
        DEFAULT_WEIGHTS,
    )
    assert story_selection is not None
    assert story_selection.effective_weights == STORY_WEIGHTS
    assert story_selection.effective_source == models.NARRATIVE_OUTCOME_SOURCE_STORY

    inherited = service.get_session_selection("s_forest001", DEFAULT_WEIGHTS)
    assert inherited is not None
    assert inherited.story_weights == STORY_WEIGHTS
    assert inherited.session_weights is None
    assert inherited.effective_weights == STORY_WEIGHTS

    overridden = service.set_session_weights(
        "s_forest001",
        SESSION_WEIGHTS,
        DEFAULT_WEIGHTS,
    )
    assert overridden is not None
    assert overridden.effective_weights == SESSION_WEIGHTS
    assert overridden.effective_source == models.NARRATIVE_OUTCOME_SOURCE_SESSION

    cleared_session = service.set_session_weights(
        "s_forest001",
        None,
        DEFAULT_WEIGHTS,
    )
    assert cleared_session is not None
    assert cleared_session.session_weights is None
    assert cleared_session.effective_weights == STORY_WEIGHTS

    cleared_story = service.set_story_weights(
        story.workspace_id,
        story.id,
        None,
        DEFAULT_WEIGHTS,
    )
    assert cleared_story is not None
    assert cleared_story.story_weights is None
    assert cleared_story.effective_weights == DEFAULT_WEIGHTS


def test_outcome_record_typed_round_trip_and_unique_turn(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "narrative-records.sqlite3")
    service = gateway.narrative_outcomes

    created = service.record(
        session_id="s_forest001",
        turn_id=99,
        outcome_code="success_with_cost",
        reason="冒险穿过摇晃的吊桥",
        actor="Alice",
        sample_value=58,
        effective_weights=SESSION_WEIGHTS,
        effective_source=models.NARRATIVE_OUTCOME_SOURCE_SESSION,
    )

    loaded = service.get_for_turn("s_forest001", 99)
    assert loaded == created
    assert loaded is not None
    assert loaded.effective_weights == SESSION_WEIGHTS
    assert service.list_for_turns("s_forest001", [98, 99, 100]) == [created]

    with pytest.raises(IntegrityError):
        service.record(
            session_id="s_forest001",
            turn_id=99,
            outcome_code="success",
            reason="重复裁定",
            actor="",
            sample_value=10,
            effective_weights=DEFAULT_WEIGHTS,
            effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
        )

    assert service.delete_from_turn("s_forest001", 99) == 1
    assert service.get_for_turn("s_forest001", 99) is None
