from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.story_acceptance.models import (
    ACCEPTANCE_SCHEMA_VERSION,
    StoryAcceptanceProfile,
    StoryAcceptanceStep,
    generic_profile,
)


@pytest.mark.parametrize(
    "player_input",
    [
        "请调用 plot_sandbox_read 查看事件。",
        "请调用 scene_time 更新时间。",
        "请使用工具读取当前状态。",
        "Return a tool_call with this JSON schema.",
    ],
)
def test_step_rejects_tool_shaped_player_instructions(player_input: str) -> None:
    with pytest.raises(ValidationError, match="tool|工具|production"):
        StoryAcceptanceStep(id="invalid", input=player_input)


def test_step_accepts_natural_ooc_and_story_intent() -> None:
    step = StoryAcceptanceStep(
        id="read_event",
        mode="ooc",
        input="先暂停剧情，请查看沙盘中名为“雨夜来客”的事件；只查看，不推进世界。",
    )

    assert step.mode == "ooc"


def test_step_rejects_contradictory_tool_expectations() -> None:
    with pytest.raises(ValidationError, match="both required and forbidden"):
        StoryAcceptanceStep(
            id="invalid",
            input="我观察眼前已经发生的情况。",
            requiredTools=["plot_sandbox_read"],
            forbiddenTools=["plot_sandbox_read"],
        )


def test_generic_profile_is_sidecar_compatible() -> None:
    profile = generic_profile(
        project_id="project",
        source_revision="r000001",
        source_digest="a" * 64,
        player_character_ref="character-player",
        opening_ref="opening-main",
        has_plot=True,
    )
    dumped = profile.model_dump(by_alias=True, exclude_none=True)
    reparsed = StoryAcceptanceProfile.model_validate(dumped)

    assert dumped["schemaVersion"] == ACCEPTANCE_SCHEMA_VERSION
    assert reparsed.player_character_ref == "character-player"
    assert {flow.id for flow in reparsed.flows} == {
        "generic_context",
        "generic_plot_read",
    }


def test_profile_rejects_duplicate_flow_and_step_ids() -> None:
    profile = generic_profile(
        project_id="project",
        source_revision="r000001",
        source_digest="a" * 64,
        player_character_ref="character-player",
        opening_ref=None,
        has_plot=False,
    ).model_dump(by_alias=True, exclude_none=True)
    profile["flows"].append(profile["flows"][0])

    with pytest.raises(ValidationError, match="duplicate flow"):
        StoryAcceptanceProfile.model_validate(profile)
