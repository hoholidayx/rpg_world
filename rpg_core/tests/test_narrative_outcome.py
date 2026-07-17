from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rpg_core.tooling.base import BaseTool
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


class _StateTool(BaseTool):
    description = "state test tool"

    def __init__(self, name: str) -> None:
        self.name = name

    def parameters(self) -> dict[str, object]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: object) -> str:
        del kwargs
        return "ok"


class _SceneCapabilities:
    def __init__(self, *names: str) -> None:
        self._names = names

    def get_tools(self) -> list[BaseTool]:
        return [_StateTool(name) for name in self._names]


class _NormalStatusCapabilities:
    session_id = "s1"

    @staticmethod
    def list_context_tables() -> list[dict[str, object]]:
        return [{
            "id": 1,
            "document": {
                "rows": [{"key": "生命", "value": "10", "updateFrequency": "realtime"}],
            },
        }]


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
        scene_tracker=_SceneCapabilities("scene_attr"),
        status_manager=_NormalStatusCapabilities(),
    )
    module.bind_turn(scratch)  # type: ignore[arg-type]
    try:
        module.adjudicate(reason="能否说服守门人", actor="Alice")
        fixed_sections = module.get_fixed_sections()
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

    assert fixed_sections == []
    assert inspection_sections == []
    assert len(sections) == 1
    content = sections[0].content
    assert '"outcomeCode":"setback"' in content
    assert '"label":"失败但推进"' in content
    assert '"reason":"能否说服守门人"' in content
    assert '"actor":"Alice"' in content
    assert "本轮裁定已完成，直接执行以下最终结果" in content
    assert "rp_story_outcome" not in content
    assert "不得改判" in content
    assert "reason 是不可缩小的整体目标边界" in content
    assert "本轮实际提供的状态工具（scene_attr、status_table_set_values）" in content
    assert "scene_time" not in content
    assert "scene_del_attr" not in content
    assert "输出任何 RP 正文前调用" in content
    assert "工具调用轮不得夹带 RP 正文" in content
    assert "状态同步无需玩家确认" in content
    assert "不得询问是否需要更新状态" in content
    assert "StatusSubAgent" not in content
    assert "sample" not in content
    assert "weights" not in content


def test_staged_outcome_lists_opted_in_scene_tools_without_normal_writer() -> None:
    module = NarrativeOutcomeModule(
        session_id="s1",
        rng=_SequenceRng(6),  # type: ignore[arg-type]
    )
    scratch = SimpleNamespace(
        turn_id=10,
        narrative_outcome_selection=None,
        narrative_outcome=None,
        scene_tracker=_SceneCapabilities(
            "scene_time",
            "scene_attr",
            "scene_del_attr",
        ),
        status_manager=None,
    )
    module.bind_turn(scratch)  # type: ignore[arg-type]
    try:
        module.adjudicate(reason="穿过风暴")
        sections = module.get_runtime_sections(ModuleContextRequest(
            session_id="s1",
            include_staged_turn=True,
        ))
    finally:
        module.unbind_turn(scratch)  # type: ignore[arg-type]

    content = sections[0].content
    assert "本轮实际提供的状态工具（scene_time、scene_attr、scene_del_attr）" in content
    assert "status_table_set_values" not in content


def test_staged_outcome_does_not_name_unavailable_state_tools() -> None:
    module = NarrativeOutcomeModule(
        session_id="s1",
        rng=_SequenceRng(6),  # type: ignore[arg-type]
    )
    scratch = SimpleNamespace(
        turn_id=11,
        narrative_outcome_selection=None,
        narrative_outcome=None,
        scene_tracker=None,
        status_manager=None,
    )
    module.bind_turn(scratch)  # type: ignore[arg-type]
    try:
        module.adjudicate(reason="等待天亮")
        sections = module.get_runtime_sections(ModuleContextRequest(
            session_id="s1",
            include_staged_turn=True,
        ))
    finally:
        module.unbind_turn(scratch)  # type: ignore[arg-type]

    content = sections[0].content
    assert "本轮没有提供状态写入工具" in content
    assert "scene_" not in content
    assert "status_table_set_values" not in content
