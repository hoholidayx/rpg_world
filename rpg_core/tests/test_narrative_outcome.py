from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rpg_core.rp_modules.narrative_outcome import (
    NarrativeOutcomeModule,
    NarrativeOutcomeSampler,
)
from rpg_core.rp_modules.narrative_outcome.models import (
    NARRATIVE_OUTCOME_DEFINITION_BY_CODE,
    NarrativeOutcomeSelection,
)
from rpg_core.rp_modules.models import ModuleContextRequest
from rpg_core.settings import NarrativeOutcomeModuleSettings
from rpg_data import models


DEFAULT_WEIGHTS = models.NarrativeOutcomeWeights()


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        (1, "critical_success"),
        (5, "critical_success"),
        (6, "success"),
        (30, "success"),
        (31, "success_with_cost"),
        (70, "success_with_cost"),
        (71, "setback"),
        (95, "setback"),
        (96, "critical_failure"),
        (100, "critical_failure"),
    ],
)
def test_default_cumulative_boundaries(sample: int, expected: str) -> None:
    definition = NarrativeOutcomeSampler.definition_for_sample(
        sample,
        DEFAULT_WEIGHTS,
    )
    assert definition.code == expected


def test_zero_weight_tiers_are_skipped() -> None:
    weights = models.NarrativeOutcomeWeights(
        critical_success=0,
        success=0,
        success_with_cost=100,
        setback=0,
        critical_failure=0,
    )
    assert NarrativeOutcomeSampler.definition_for_sample(1, weights).code == "success_with_cost"
    assert NarrativeOutcomeSampler.definition_for_sample(100, weights).code == "success_with_cost"


def test_outcome_guidance_preserves_whole_goal_boundaries() -> None:
    critical_success = NARRATIVE_OUTCOME_DEFINITION_BY_CODE["critical_success"].narrative_guidance
    success = NARRATIVE_OUTCOME_DEFINITION_BY_CODE["success"].narrative_guidance
    success_with_cost = NARRATIVE_OUTCOME_DEFINITION_BY_CODE["success_with_cost"].narrative_guidance
    setback = NARRATIVE_OUTCOME_DEFINITION_BY_CODE["setback"].narrative_guidance
    critical_failure = NARRATIVE_OUTCOME_DEFINITION_BY_CODE["critical_failure"].narrative_guidance

    assert "完整且超额达成 reason 描述的整体目标" in critical_success
    assert "完整达成 reason 描述的整体目标" in success
    assert "不得只完成子步骤" in success_with_cost
    assert "代价不得抵消整体目标已经达成" in success_with_cost
    assert "未达成 reason 描述的整体目标" in setback
    assert "未达成 reason 描述的整体目标" in critical_failure


class _SequenceRng:
    def __init__(self, *values: int) -> None:
        self.values = list(values)
        self.calls = 0

    def randint(self, lower: int, upper: int) -> int:
        assert (lower, upper) == (1, 100)
        self.calls += 1
        return self.values.pop(0)


@pytest.mark.asyncio
async def test_same_turn_reuses_staged_result_and_hides_random_details() -> None:
    rng = _SequenceRng(31, 100)
    selection = NarrativeOutcomeSelection(
        effective_weights=DEFAULT_WEIGHTS,
        effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
    )
    module = NarrativeOutcomeModule(
        session_id="s1",
        settings=NarrativeOutcomeModuleSettings(),
        rng=rng,  # type: ignore[arg-type]
        selection=selection,
    )
    scratch = SimpleNamespace(
        turn_id=7,
        narrative_outcome_selection=None,
        narrative_outcome=None,
    )
    module.bind_turn(scratch)  # type: ignore[arg-type]
    try:
        first = module.adjudicate(reason="潜过守卫", actor="Alice")
        second = module.adjudicate(reason="重复调用", actor="Bob")
        tool_result = await module.get_tools()[0].execute(
            reason="第三次调用",
            actor="Carol",
        )
    finally:
        module.unbind_turn(scratch)  # type: ignore[arg-type]

    assert first is second
    assert rng.calls == 1
    assert first.outcome_code == "success_with_cost"
    payload = json.loads(tool_result)
    assert payload == {
        "outcomeCode": "success_with_cost",
        "label": "成功但有代价",
        "narrativeGuidance": (
            "完整达成 reason 描述的整体目标，同时引入一个与行动相称的代价或复杂化；"
            "不得只完成子步骤，代价不得抵消整体目标已经达成。"
        ),
        "reason": "潜过守卫",
        "actor": "Alice",
    }
    assert "sample" not in tool_result
    assert "weights" not in tool_result


def test_staged_outcome_is_injected_into_main_runtime_before_generation() -> None:
    rng = _SequenceRng(71)
    selection = NarrativeOutcomeSelection(
        effective_weights=DEFAULT_WEIGHTS,
        effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
    )
    module = NarrativeOutcomeModule(
        session_id="s1",
        settings=NarrativeOutcomeModuleSettings(),
        rng=rng,  # type: ignore[arg-type]
        selection=selection,
    )
    scratch = SimpleNamespace(
        turn_id=9,
        narrative_outcome_selection=None,
        narrative_outcome=None,
    )
    module.bind_turn(scratch)  # type: ignore[arg-type]
    try:
        module.adjudicate(reason="能否说服守门人", actor="Alice")
        inspection_sections = module.get_runtime_sections(
            ModuleContextRequest(session_id="s1", user_input="")
        )
        sections = module.get_runtime_sections(
            ModuleContextRequest(
                session_id="s1",
                user_input="请让我进去",
                include_staged_turn=True,
            )
        )
    finally:
        module.unbind_turn(scratch)  # type: ignore[arg-type]

    assert inspection_sections == []
    assert len(sections) == 1
    content = sections[0].content
    assert '"outcomeCode":"setback"' in content
    assert '"label":"失败但推进"' in content
    assert '"reason":"能否说服守门人"' in content
    assert '"actor":"Alice"' in content
    assert "不得改判" in content
    assert "reason 是本次裁定不可缩小的整体目标边界" in content
    assert "输出任何 RP 正文前调用" in content
    assert "工具调用轮不得夹带 RP 正文" in content
    assert "状态同步无需玩家确认" in content
    assert "不得询问是否需要标记、记录或更新状态" in content
    assert "StatusSubAgent" not in content
    assert "sample" not in content
    assert "weights" not in content
